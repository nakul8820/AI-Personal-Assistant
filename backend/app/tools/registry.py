"""Gemini function declarations + name->callable dispatch.

Declarations are plain dicts (Gemini REST `function_declarations` format), so no
SDK dependency. `dispatch()` parses JSON args into typed models and calls the
Sprint-1 functions, returning a JSON-serializable dict.
"""

from datetime import date, datetime

from app.models.schemas import CalendarEventUpdate, TaskUpdate
from app.tools import calendar, contacts, tasks

# Tools whose execution mutates/destroys and must pass the confirmation gate.
DESTRUCTIVE = {"delete_calendar_event", "delete_task", "complete_task"}
# Read tools that produce candidate lists for two-phase mutation.
SEARCH = {"search_calendar_events", "list_tasks", "search_contacts"}

_STR = {"type": "string"}


DECLARATIONS: list[dict] = [
    {
        "name": "search_calendar_events",
        "description": "Search the user's calendar within a date range. Use before any update/delete to find the real event id.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text match; '' for all."},
                "date_range_start": {"type": "string", "description": "ISO-8601 with offset."},
                "date_range_end": {"type": "string", "description": "ISO-8601 with offset."},
            },
            "required": ["query", "date_range_start", "date_range_end"],
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Create a calendar event. Requires title and start.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": _STR,
                "start": {"type": "string", "description": "ISO-8601 with offset."},
                "end": {"type": "string", "description": "ISO-8601 with offset. Default +30min."},
                "attendees": {"type": "array", "items": _STR},
                "description": _STR,
            },
            "required": ["title", "start", "end"],
        },
    },
    {
        "name": "update_calendar_event",
        "description": "Update an event by verified id. For reschedules/edits.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": _STR,
                "title": _STR,
                "start": {"type": "string", "description": "ISO-8601 with offset."},
                "end": {"type": "string", "description": "ISO-8601 with offset."},
                "attendees": {"type": "array", "items": _STR},
                "description": _STR,
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete an event by verified id. Requires user confirmation.",
        "parameters": {
            "type": "object",
            "properties": {"event_id": _STR},
            "required": ["event_id"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List tasks, optionally filtered by due-date range and status.",
        "parameters": {
            "type": "object",
            "properties": {
                "due_range_start": {"type": "string", "description": "YYYY-MM-DD"},
                "due_range_end": {"type": "string", "description": "YYYY-MM-DD"},
                "status": {"type": "string", "enum": ["needsAction", "completed", "all"]},
            },
        },
    },
    {
        "name": "create_task",
        "description": "Create a task. Requires title.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": _STR,
                "due": {"type": "string", "description": "YYYY-MM-DD"},
                "notes": _STR,
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_task",
        "description": "Update a task by verified id.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": _STR,
                "title": _STR,
                "due": {"type": "string", "description": "YYYY-MM-DD"},
                "notes": _STR,
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task complete by verified id. Requires user confirmation.",
        "parameters": {
            "type": "object",
            "properties": {"task_id": _STR},
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a task by verified id. Requires user confirmation.",
        "parameters": {
            "type": "object",
            "properties": {"task_id": _STR},
            "required": ["task_id"],
        },
    },
    {
        "name": "search_contacts",
        "description": "Find a contact by name when the user wants to invite/meet that person.",
        "parameters": {
            "type": "object",
            "properties": {"name": _STR},
            "required": ["name"],
        },
    },
    {
        "name": "query_activity_log",
        "description": "Query the log of historical actions/tool calls performed by the assistant. Use this to answer questions about what meetings, tasks, or changes the user has created, updated, completed, or deleted in the past.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Specific date in YYYY-MM-DD format to query, or omit to query all historical logs."},
                "limit": {"type": "integer", "description": "Maximum number of recent log entries to retrieve. Default is 50."},
            },
        },
    },
]


def _dt(v: str, tz_str: str = "UTC") -> datetime:
    dt = datetime.fromisoformat(v)
    # Self-healing migration for fallback models (like open-weight ones) that
    # output "+00:00" or "Z" by mistake instead of applying the user's local offset.
    if tz_str != "UTC" and dt.tzinfo is not None:
        clean_v = v.strip()
        if (
            clean_v.endswith("Z")
            or clean_v.endswith("+00:00")
            or clean_v.endswith("-00:00")
            or clean_v.endswith("+0000")
            or clean_v.endswith("-0000")
        ):
            from zoneinfo import ZoneInfo
            try:
                user_tz = ZoneInfo(tz_str)
                # Keep the generated date/time digits but treat them as local to the user
                return dt.replace(tzinfo=None).replace(tzinfo=user_tz)
            except Exception:
                pass
    return dt


def _date(v: str) -> date:
    return date.fromisoformat(v[:10])


def dispatch(user_id: str, name: str, args: dict, tz_str: str = "UTC") -> dict:
    """Run a tool call. Returns a JSON-serializable result dict."""
    if name == "search_calendar_events":
        res = calendar.search_calendar_events(
            user_id, args.get("query", ""),
            _dt(args["date_range_start"], tz_str), _dt(args["date_range_end"], tz_str),
        )
        return {"events": [e.model_dump(mode="json") for e in res]}

    if name == "create_calendar_event":
        e = calendar.create_calendar_event(
            user_id, args["title"], _dt(args["start"], tz_str), _dt(args["end"], tz_str),
            attendees=args.get("attendees") or [],
            description=args.get("description"),
        )
        return {"event": e.model_dump(mode="json")}

    if name == "update_calendar_event":
        upd = CalendarEventUpdate(
            title=args.get("title"),
            start=_dt(args["start"], tz_str) if args.get("start") else None,
            end=_dt(args["end"], tz_str) if args.get("end") else None,
            attendees=args.get("attendees"),
            description=args.get("description"),
        )
        e = calendar.update_calendar_event(user_id, args["event_id"], upd)
        return {"event": e.model_dump(mode="json")}

    if name == "delete_calendar_event":
        return calendar.delete_calendar_event(user_id, args["event_id"]).model_dump()

    if name == "list_tasks":
        res = tasks.list_tasks(
            user_id,
            due_range_start=_date(args["due_range_start"]) if args.get("due_range_start") else None,
            due_range_end=_date(args["due_range_end"]) if args.get("due_range_end") else None,
            status=args.get("status", "needsAction"),
        )
        return {"tasks": [t.model_dump(mode="json") for t in res]}

    if name == "create_task":
        t = tasks.create_task(
            user_id, args["title"],
            due=_date(args["due"]) if args.get("due") else None,
            notes=args.get("notes"),
        )
        return {"task": t.model_dump(mode="json")}

    if name == "update_task":
        upd = TaskUpdate(
            title=args.get("title"),
            due=_date(args["due"]) if args.get("due") else None,
            notes=args.get("notes"),
        )
        t = tasks.update_task(user_id, args["task_id"], upd)
        return {"task": t.model_dump(mode="json")}

    if name == "complete_task":
        return {"task": tasks.complete_task(user_id, args["task_id"]).model_dump(mode="json")}

    if name == "delete_task":
        return tasks.delete_task(user_id, args["task_id"]).model_dump()

    if name == "search_contacts":
        res = contacts.search_contacts(user_id, args["name"])
        return {"contacts": [c.model_dump() for c in res]}

    if name == "query_activity_log":
        from app.memory import store
        res = store.query_action_log(
            user_id,
            date=args.get("date"),
            limit=args.get("limit", 50),
        )
        return {"activity_log": res}

    raise ValueError(f"Unknown tool: {name}")
