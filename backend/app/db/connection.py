"""Unified Database Adapter for PostgreSQL and SQLite.

If DATABASE_URL is set (starting with postgresql:// or postgres://), connects to PostgreSQL.
If PostgreSQL is unreachable or unsupported, gracefully falls back to local SQLite at settings.db_path.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Generator

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from app.core.config import get_settings

logger = logging.getLogger("db")


# ── Schemas ───────────────────────────────────────────────────────────────────

SQLITE_TOKENS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    user_id         TEXT PRIMARY KEY,
    email           TEXT,
    blob            BLOB NOT NULL,
    last_active_at  TIMESTAMP
);
"""

POSTGRES_TOKENS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    user_id         VARCHAR PRIMARY KEY,
    email           VARCHAR,
    blob            TEXT NOT NULL,
    last_active_at  TIMESTAMPTZ
);
"""

SQLITE_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS day_sessions (
    user_id         TEXT NOT NULL,
    date            TEXT NOT NULL,
    history         TEXT NOT NULL DEFAULT '[]',
    known_items     TEXT NOT NULL DEFAULT '{}',
    state           TEXT NOT NULL DEFAULT 'AWAITING_INPUT',
    pending_action  TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS action_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL,
    date            TEXT NOT NULL,
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_message    TEXT,
    tool_name       TEXT NOT NULL,
    tool_args       TEXT,
    result_summary  TEXT,
    provider        TEXT,
    api_hits        INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_action_log_user_date ON action_log (user_id, date);
"""

POSTGRES_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS day_sessions (
    user_id         VARCHAR NOT NULL,
    date            VARCHAR NOT NULL,
    history         TEXT NOT NULL DEFAULT '[]',
    known_items     TEXT NOT NULL DEFAULT '{}',
    state           VARCHAR NOT NULL DEFAULT 'AWAITING_INPUT',
    pending_action  TEXT,
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS action_log (
    id              SERIAL PRIMARY KEY,
    user_id         VARCHAR NOT NULL,
    date            VARCHAR NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_message    TEXT,
    tool_name       VARCHAR NOT NULL,
    tool_args       TEXT,
    result_summary  TEXT,
    provider        VARCHAR,
    api_hits        INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_action_log_user_date ON action_log (user_id, date);
"""

_pg_initialized = False
_sqlite_initialized = False
_postgres_disabled = False


class UnifiedCursor:
    """Wrapper that provides dict-style access for rows across SQLite and Postgres."""
    def __init__(self, cursor, is_postgres: bool):
        self.cursor = cursor
        self.is_postgres = is_postgres

    def execute(self, query: str, params: tuple = ()):
        if self.is_postgres:
            # Replace ? with %s if SQLite query format passed
            query_pg = query.replace("?", "%s")
            clean_params = []
            for p in params:
                if isinstance(p, (bytes, memoryview)):
                    clean_params.append(bytes(p).decode("utf-8", errors="replace"))
                else:
                    clean_params.append(p)
            self.cursor.execute(query_pg, tuple(clean_params))
        else:
            # Replace %s with ? if Postgres query format passed
            query_lite = query.replace("%s", "?")
            self.cursor.execute(query_lite, params)
        return self

    def fetchone(self) -> dict | None:
        row = self.cursor.fetchone()
        if not row:
            return None
        return dict(row)

    def fetchall(self) -> list[dict]:
        rows = self.cursor.fetchall()
        if not rows:
            return []
        return [dict(r) for r in rows]


@contextmanager
def get_db() -> Generator[UnifiedCursor, None, None]:
    global _pg_initialized, _sqlite_initialized, _postgres_disabled
    settings = get_settings()
    db_url = settings.database_url.strip()

    is_postgres = (
        not _postgres_disabled
        and (db_url.startswith("postgresql://") or db_url.startswith("postgres://"))
    )

    if is_postgres and HAS_PSYCOPG2:
        if db_url.startswith("postgres://"):
            db_url = "postgresql://" + db_url[len("postgres://"):]

        try:
            conn = psycopg2.connect(
                db_url,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=3,
            )
            cursor = conn.cursor()
            try:
                if not _pg_initialized:
                    cursor.execute(POSTGRES_TOKENS_SCHEMA)
                    cursor.execute(POSTGRES_MEMORY_SCHEMA)
                    conn.commit()
                    _pg_initialized = True
                yield UnifiedCursor(cursor, is_postgres=True)
                conn.commit()
                return
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()
                conn.close()
        except Exception as e:
            logger.warning(
                "PostgreSQL connection failed (%s). Disabling PostgreSQL and switching to local SQLite (%s).",
                e,
                settings.db_path,
            )
            _postgres_disabled = True

    # Local SQLite Fallback
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        if not _sqlite_initialized:
            conn.executescript(SQLITE_TOKENS_SCHEMA)
            conn.executescript(SQLITE_MEMORY_SCHEMA)
            try:
                conn.execute("ALTER TABLE tokens ADD COLUMN last_active_at TIMESTAMP")
            except sqlite3.OperationalError:
                pass
            conn.commit()
            _sqlite_initialized = True
        yield UnifiedCursor(cursor, is_postgres=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
