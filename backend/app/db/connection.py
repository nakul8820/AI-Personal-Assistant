"""PostgreSQL / Supabase Database Adapter (SQLite removed per user request).

Supports direct PostgreSQL connections as well as automatic IPv4 Pooler resolution
for Supabase instances hosted on IPv6-restricted environments like Render.
"""

import json
import logging
import re
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
_working_db_url: str | None = None


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


def _build_candidate_urls(raw_url: str) -> list[str]:
    """Generate connection URL candidates, adding IPv4 Supabase poolers if direct IPv6 URL is provided."""
    candidates = []
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    candidates.append(url)

    # If Supabase direct domain `db.<ref>.supabase.co` is present, generate IPv4 pooler candidate URLs
    match = re.search(r"postgresql://([^:]+):([^@]+)@db\.([a-z0-9]+)\.supabase\.co(?::\d+)?/(.+)", url)
    if match:
        user, pwd, ref, dbname = match.groups()
        # Pooler requires username in format `postgres.<ref>`
        pooler_user = f"postgres.{ref}" if not user.endswith(f".{ref}") else user
        regions = [
            "aws-0-ap-south-1.pooler.supabase.com",
            "aws-0-us-east-1.pooler.supabase.com",
            "aws-0-eu-central-1.pooler.supabase.com",
            "aws-0-ap-southeast-1.pooler.supabase.com",
            "aws-0-us-west-1.pooler.supabase.com",
        ]
        for region_host in regions:
            candidates.append(f"postgresql://{pooler_user}:{pwd}@{region_host}:6543/{dbname}")
            candidates.append(f"postgresql://{pooler_user}:{pwd}@{region_host}:5432/{dbname}")

    return candidates


@contextmanager
def get_db() -> Generator[UnifiedCursor, None, None]:
    global _pg_initialized, _working_db_url
    if not HAS_PSYCOPG2:
        raise ImportError(
            "psycopg2 is required to connect to PostgreSQL. Run `pip install psycopg2-binary`."
        )

    settings = get_settings()
    raw_url = settings.database_url.strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is not set in environment variables.")

    conn = None
    last_err = None

    # Use cached working URL if already validated
    urls_to_try = [_working_db_url] if _working_db_url else _build_candidate_urls(raw_url)

    for db_url in urls_to_try:
        try:
            conn = psycopg2.connect(
                db_url,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=5,
            )
            _working_db_url = db_url
            break
        except Exception as e:
            last_err = e
            logger.warning("PostgreSQL connection attempt failed for %s: %s", db_url.split("@")[-1], e)

    if conn is None:
        raise RuntimeError(f"Could not connect to PostgreSQL/Supabase database. Error: {last_err}")

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
