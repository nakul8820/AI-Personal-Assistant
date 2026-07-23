"""Google Calendar tool functions. Pure-ish: (user_id, args) -> pydantic models."""

import logging
from datetime import datetime

from app.core.errors import NotFoundError
from app.models.schemas import (
    CalendarEventSummary,
    CalendarEventUpdate,
    DeleteResult,
)
from app.tools._google import guarded, service

logger = logging.getLogger("tools.calendar")


def _cal(user_id: str):
    return service(user_id, "calendar", "v3")


def _to_summary(ev: dict) -> CalendarEventSummary:
    start = ev.get("start", {})
    end = ev.get("end", {})
    return CalendarEventSummary(
        id=ev["id"],
        title=ev.get("summary", "(no title)"),
        start=start.get("dateTime") or start.get("date"),
        end=end.get("dateTime") or end.get("date"),
        attendees=[a["email"] for a in ev.get("attendees", []) if a.get("email")],
        recurring_event_id=ev.get("recurringEventId"),
        html_link=ev.get("htmlLink"),
    )


@guarded
def search_calendar_events(
    user_id: str,
    query: str,
    date_range_start: datetime,
    date_range_end: datetime,
) -> list[CalendarEventSummary]:
    logger.info("search_calendar_events | user=%s | query=%r | start=%s | end=%s", user_id, query, date_range_start, date_range_end)
    res = (
        _cal(user_id)
        .events()
        .list(
            calendarId="primary",
            q=query or None,
            timeMin=date_range_start.isoformat(),
            timeMax=date_range_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        )
        .execute()
    )
    items = [_to_summary(e) for e in res.get("items", [])]
    logger.info("search_calendar_events found | count=%d", len(items))
    return items


@guarded
def create_calendar_event(
    user_id: str,
    title: str,
    start: datetime,
    end: datetime,
    attendees: list[str] | None = None,
    description: str | None = None,
) -> CalendarEventSummary:
    logger.info("create_calendar_event | title=%r | start=%s | end=%s | attendees=%s", title, start, end, attendees)
    body = {
        "summary": title,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]
    if description:
        body["description"] = description
    ev = (
        _cal(user_id)
        .events()
        .insert(calendarId="primary", body=body, sendUpdates="all")
        .execute()
    )
    summary = _to_summary(ev)
    logger.info("create_calendar_event created | id=%s", summary.id)
    return summary


@guarded
def update_calendar_event(
    user_id: str, event_id: str, updates: CalendarEventUpdate
) -> CalendarEventSummary:
    logger.info("update_calendar_event | id=%s", event_id)
    body: dict = {}
    if updates.title is not None:
        body["summary"] = updates.title
    if updates.start is not None:
        body["start"] = {"dateTime": updates.start.isoformat()}
    if updates.end is not None:
        body["end"] = {"dateTime": updates.end.isoformat()}
    if updates.attendees is not None:
        body["attendees"] = [{"email": str(e)} for e in updates.attendees]
    if updates.description is not None:
        body["description"] = updates.description
    if not body:
        raise NotFoundError("No fields to update.")
    ev = (
        _cal(user_id)
        .events()
        .patch(
            calendarId="primary",
            eventId=event_id,
            body=body,
            sendUpdates="all",
        )
        .execute()
    )
    return _to_summary(ev)


@guarded
def delete_calendar_event(user_id: str, event_id: str) -> DeleteResult:
    logger.info("delete_calendar_event | id=%s", event_id)
    _cal(user_id).events().delete(
        calendarId="primary", eventId=event_id, sendUpdates="all"
    ).execute()
    return DeleteResult(id=event_id)
