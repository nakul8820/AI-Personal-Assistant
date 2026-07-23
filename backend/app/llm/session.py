"""DB-backed conversation state, keyed by user_id + calendar date.

The stable session key is:  "{user_id}:{YYYY-MM-DD}"
  - Same all day regardless of page reloads or tab switches
  - Automatically resets at midnight (new day = new key = fresh context)
  - History is persisted to SQLite via app.memory.store
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo

from app.memory.store import (
    load_day_session,
    save_day_session,
    trim_history_for_llm,
)

logger = logging.getLogger("memory.session")


class State(str, Enum):
    AWAITING_INPUT = "AWAITING_INPUT"
    AWAITING_DISAMBIGUATION = "AWAITING_DISAMBIGUATION"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"


@dataclass
class ConversationState:
    session_id: str        # "{user_id}:{YYYY-MM-DD}"
    user_id: str
    date: str              # YYYY-MM-DD in user's local timezone
    user_timezone: str = "UTC"
    state: State = State.AWAITING_INPUT
    history: list[dict] = field(default_factory=list)   # full day history (in DB)
    pending_candidates: list[dict] | None = None
    pending_action: dict | None = None
    known_items: dict[str, dict] = field(default_factory=dict)

    def llm_history(self) -> list[dict]:
        """Return trimmed history for LLM context (last MAX_HISTORY_TURNS turns)."""
        return trim_history_for_llm(self.history)

    def save(self) -> None:
        """Persist current state to day_sessions table."""
        save_day_session(
            user_id=self.user_id,
            date=self.date,
            history=self.history,
            known_items=self.known_items,
            state=self.state.value,
            pending_action=self.pending_action,
        )
        logger.debug("Saved session | user=%s date=%s | turns=%d", self.user_id, self.date, len(self.history))


def _today_for_tz(tz_str: str) -> str:
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).strftime("%Y-%m-%d")


def make_session_id(user_id: str, tz: str = "UTC") -> str:
    """Return the stable day-scoped session key for a user."""
    return f"{user_id}:{_today_for_tz(tz)}"


def get_or_create(session_id: str, user_id: str, tz: str = "UTC") -> ConversationState:
    """Load from DB if exists, otherwise create fresh. Always returns a ConversationState."""
    # Extract date from session_id or compute fresh
    parts = session_id.rsplit(":", 1)
    if len(parts) == 2 and len(parts[1]) == 10:
        date = parts[1]
    else:
        date = _today_for_tz(tz)

    saved = load_day_session(user_id, date)
    history = saved["history"]

    # Self-heal check: guarantee every turn has a 'role' key
    for turn in history:
        if "role" not in turn:
            turn["role"] = "model"

    cs = ConversationState(
        session_id=session_id,
        user_id=user_id,
        date=date,
        user_timezone=tz,
        state=State(saved["state"]),
        history=history,
        known_items=saved["known_items"],
        pending_action=saved["pending_action"],
    )

    if saved["history"]:
        logger.info(
            "Restored session | user=%s date=%s | turns=%d known_items=%d",
            user_id, date, len(saved["history"]), len(saved["known_items"])
        )
    else:
        logger.info("New session | user=%s date=%s", user_id, date)

    return cs


def reset(session_id: str) -> None:
    """Deprecated: no-op since state is now in the DB, not memory."""
    pass
