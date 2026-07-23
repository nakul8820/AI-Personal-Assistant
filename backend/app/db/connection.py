"""PostgreSQL / Supabase Database Connection Manager.

Connects strictly to PostgreSQL using the DATABASE_URL environment variable.
"""

import logging
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

POSTGRES_TOKENS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    user_id         VARCHAR PRIMARY KEY,
    email           VARCHAR,
    blob            TEXT NOT NULL,
    last_active_at  TIMESTAMPTZ
);
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


class UnifiedCursor:
    """Wrapper that provides dict-style access for rows across Postgres."""
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query: str, params: tuple = ()):
        query_pg = query.replace("?", "%s")
        clean_params = []
        for p in params:
            if isinstance(p, (bytes, memoryview)):
                clean_params.append(bytes(p).decode("utf-8", errors="replace"))
            else:
                clean_params.append(p)
        self.cursor.execute(query_pg, tuple(clean_params))
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
    global _pg_initialized
    if not HAS_PSYCOPG2:
        raise ImportError(
            "psycopg2 is required to connect to PostgreSQL. Run `pip install psycopg2-binary`."
        )

    settings = get_settings()
    db_url = settings.database_url.strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    # Convert legacy postgres:// to postgresql:// if needed by psycopg2
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://"):]

    try:
        conn = psycopg2.connect(
            db_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10,
        )
    except Exception as e:
        logger.error("Failed to connect to PostgreSQL using DATABASE_URL: %s", e)
        raise RuntimeError(f"Database connection failed: {e}") from e

    cursor = conn.cursor()
    try:
        if not _pg_initialized:
            cursor.execute(POSTGRES_TOKENS_SCHEMA)
            cursor.execute(POSTGRES_MEMORY_SCHEMA)
            conn.commit()
            _pg_initialized = True
        yield UnifiedCursor(cursor)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
