"""Per-user encrypted token store. Supports PostgreSQL and SQLite via app.db.

Also tracks `last_active_at` for the idle-timeout security feature.
"""

import json
from datetime import datetime, timezone

from app.core.security import decrypt, encrypt
from app.db import get_db


def save(user_id: str, email: str, creds: dict) -> None:
    blob = encrypt(json.dumps(creds))
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        db.execute(
            "INSERT INTO tokens (user_id, email, blob, last_active_at) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email, blob=EXCLUDED.blob, last_active_at=EXCLUDED.last_active_at",
            (user_id, email, blob, now),
        )


def load(user_id: str) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT blob FROM tokens WHERE user_id=%s", (user_id,)).fetchone()
    if not row or not row.get("blob"):
        return None
    raw_blob = row["blob"]
    if isinstance(raw_blob, memoryview):
        raw_blob = bytes(raw_blob)
    return json.loads(decrypt(raw_blob))


def email_for(user_id: str) -> str | None:
    with get_db() as db:
        row = db.execute("SELECT email FROM tokens WHERE user_id=%s", (user_id,)).fetchone()
    return row.get("email") if row else None


def delete(user_id: str) -> None:
    with get_db() as db:
        db.execute("DELETE FROM tokens WHERE user_id=%s", (user_id,))


def touch_active(user_id: str) -> None:
    """Update last_active_at to now. Called on every authenticated API request."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as db:
        db.execute("UPDATE tokens SET last_active_at=%s WHERE user_id=%s", (now, user_id))


def get_last_active(user_id: str) -> datetime | None:
    """Return the last_active_at timestamp, or None if never set."""
    with get_db() as db:
        row = db.execute("SELECT last_active_at FROM tokens WHERE user_id=%s", (user_id,)).fetchone()
    if not row or not row.get("last_active_at"):
        return None
    val = row["last_active_at"]
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None
