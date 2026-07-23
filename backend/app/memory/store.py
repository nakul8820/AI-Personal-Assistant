"""Persistent memory store — day_sessions and action_log tables.

day_sessions: Full conversation state per user per calendar day.
              Loaded at the start of each turn; saved after every turn.
              History is capped to last MAX_HISTORY_TURNS when sent to LLM
              (full history is stored in DB for reference).

action_log:   Append-only audit trail — one row per tool call, forever.
              Powers the "Today's activity" panel in the UI.
"""

import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.db import get_db

logger = logging.getLogger("memory.store")

# Max turns kept in active LLM context window (full history stored in DB)
MAX_HISTORY_TURNS = 20


def _today(user_timezone: str = "UTC") -> str:
    """Return YYYY-MM-DD in the user's local timezone."""
    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).strftime("%Y-%m-%d")


def _format_timestamp(ts) -> str:
    """Consistently format a timestamp field to ISO string across SQLite and Postgres."""
    if not ts:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(ts)


# ── day_sessions ──────────────────────────────────────────────────────────────

def load_day_session(user_id: str, date: str) -> dict:
    """Return the day session dict for user+date, or a fresh empty one."""
    with get_db() as db:
        row = db.execute(
            "SELECT history, known_items, state, pending_action FROM day_sessions "
            "WHERE user_id=%s AND date=%s",
            (user_id, date),
        ).fetchone()
    if not row:
        logger.info("No day_session found for user=%s date=%s — starting fresh", user_id, date)
        return {
            "history": [],
            "known_items": {},
            "state": "AWAITING_INPUT",
            "pending_action": None,
        }
    return {
        "history": json.loads(row["history"]) if isinstance(row["history"], str) else row["history"],
        "known_items": json.loads(row["known_items"]) if isinstance(row["known_items"], str) else row["known_items"],
        "state": row["state"],
        "pending_action": json.loads(row["pending_action"]) if row["pending_action"] and isinstance(row["pending_action"], str) else row["pending_action"],
    }


def save_day_session(
    user_id: str,
    date: str,
    history: list,
    known_items: dict,
    state: str,
    pending_action: dict | None,
) -> None:
    """Upsert the day session. Called after every completed turn."""
    with get_db() as db:
        db.execute(
            """
            INSERT INTO day_sessions (user_id, date, history, known_items, state, pending_action, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, date) DO UPDATE SET
                history=EXCLUDED.history,
                known_items=EXCLUDED.known_items,
                state=EXCLUDED.state,
                pending_action=EXCLUDED.pending_action,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                user_id,
                date,
                json.dumps(history),
                json.dumps(known_items),
                state,
                json.dumps(pending_action) if pending_action else None,
            ),
        )
    logger.debug("Saved day_session | user=%s date=%s | turns=%d", user_id, date, len(history))


def trim_history_for_llm(history: list) -> list:
    """Return only the last MAX_HISTORY_TURNS items for LLM context.
    
    Adjusts the slice start index backward if it lands on a tool response message,
    preventing tool responses from being detached from their preceding assistant 
    model turns (which crashes OpenRouter/OpenAI API parsing).
    """
    if len(history) <= MAX_HISTORY_TURNS:
        return history

    start_idx = len(history) - MAX_HISTORY_TURNS

    def _is_tool_response(turn: dict) -> bool:
        parts = turn.get("parts", [])
        return any("functionResponse" in p for p in parts)

    while start_idx > 0 and _is_tool_response(history[start_idx]):
        start_idx -= 1

    return history[start_idx:]


# ── action_log ────────────────────────────────────────────────────────────────

def log_action(
    user_id: str,
    date: str,
    user_message: str,
    tool_name: str,
    tool_args: dict | None = None,
    result_summary: str | None = None,
    provider: str | None = None,
    api_hits: int = 0,
    total_tokens: int = 0,
) -> None:
    """Append one tool-call record to the action log."""
    with get_db() as db:
        db.execute(
            """
            INSERT INTO action_log
                (user_id, date, user_message, tool_name, tool_args, result_summary, provider, api_hits, total_tokens)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                date,
                user_message,
                tool_name,
                json.dumps(tool_args) if tool_args else None,
                result_summary,
                provider,
                api_hits,
                total_tokens,
            ),
        )
    logger.debug("action_log | user=%s tool=%s summary=%s", user_id, tool_name, result_summary)


def get_today_actions(user_id: str, date: str) -> list[dict]:
    """Return all action log entries for user on date, newest-first."""
    with get_db() as db:
        rows = db.execute(
            "SELECT timestamp, tool_name, tool_args, result_summary, provider, api_hits, total_tokens "
            "FROM action_log WHERE user_id=%s AND date=%s ORDER BY id DESC",
            (user_id, date),
        ).fetchall()
    
    result = []
    for r in rows:
        r_dict = dict(r)
        r_dict["timestamp"] = _format_timestamp(r_dict.get("timestamp"))
        result.append(r_dict)
    return result


def get_history_for_ui(user_id: str, date: str) -> list[dict]:
    """Return the stored history as a list of {role, text} pairs for UI restore."""
    session = load_day_session(user_id, date)
    ui_items = []
    for turn in session["history"]:
        role = turn.get("role", "")
        parts = turn.get("parts", [])
        for part in parts:
            if "text" in part and part["text"].strip():
                ui_role = "user" if role == "user" else "assistant"
                if "functionResponse" not in part:
                    ui_items.append({"role": ui_role, "text": part["text"].strip()})
    return ui_items


def query_action_log(user_id: str, date: str | None = None, limit: int = 50) -> list[dict]:
    """Retrieve historical action log entries for a user, optionally filtered by date."""
    with get_db() as db:
        if date:
            rows = db.execute(
                "SELECT timestamp, tool_name, tool_args, result_summary "
                "FROM action_log WHERE user_id=%s AND date=%s ORDER BY id DESC LIMIT %s",
                (user_id, date, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT date, timestamp, tool_name, tool_args, result_summary "
                "FROM action_log WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
    
    result = []
    for r in rows:
        r_dict = dict(r)
        r_dict["timestamp"] = _format_timestamp(r_dict.get("timestamp"))
        result.append(r_dict)
    return result
