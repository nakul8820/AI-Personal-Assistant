import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request

from app.auth import store as auth_store
from app.core.config import get_settings
from app.core.errors import GoogleAuthError, SessionTimedOut

logger = logging.getLogger("auth")


def current_user(request: Request) -> str:
    """Return the logged-in user_id (email) or raise AUTH_EXPIRED / SESSION_TIMEOUT.

    Also updates last_active_at on every successful auth check,
    and enforces the idle_timeout_minutes security window.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise GoogleAuthError("Not authenticated. Please connect your Google account.")

    s = get_settings()

    # ── Idle timeout check ────────────────────────────────────────────────────
    last_active = auth_store.get_last_active(user_id)
    if last_active is not None:
        # Normalize: ensure last_active is timezone-aware
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        idle_seconds = (datetime.now(timezone.utc) - last_active).total_seconds()
        timeout_seconds = s.idle_timeout_minutes * 60
        if idle_seconds > timeout_seconds:
            logger.warning(
                "Session idle timeout | user=%s | idle=%.0fs | limit=%ds",
                user_id, idle_seconds, timeout_seconds
            )
            raise SessionTimedOut(
                f"Session locked after {s.idle_timeout_minutes} minutes of inactivity. "
                "Please re-authenticate."
            )

    # ── Touch last_active_at ──────────────────────────────────────────────────
    auth_store.touch_active(user_id)
    return user_id
