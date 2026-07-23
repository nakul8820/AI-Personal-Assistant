"""Pydantic v2 schemas. All datetimes serialize as ISO-8601 with offset."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# ---------- Calendar ----------


class CalendarEventSummary(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = Field(default_factory=list)
    recurring_event_id: str | None = None
    html_link: str | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    attendees: list[EmailStr] | None = None
    description: str | None = None


# ---------- Tasks ----------


class TaskSummary(BaseModel):
    id: str
    title: str
    due: date | None = None
    status: Literal["needsAction", "completed"] = "needsAction"
    task_list_id: str


class TaskUpdate(BaseModel):
    title: str | None = None
    due: date | None = None
    notes: str | None = None
    status: Literal["needsAction", "completed"] | None = None


# ---------- Contacts ----------


class ContactSummary(BaseModel):
    name: str
    email: str
    source: str | None = None  # helps disambiguate "which John"


# ---------- Shared ----------


class DeleteResult(BaseModel):
    id: str
    deleted: bool = True


# ---------- Chat wire types ----------


class ChatRequest(BaseModel):
    session_id: str
    message: str
    language: str | None = None  # from STT; hints response language


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    result_summary: str | None = None
    error: str | None = None


class ChatResponse(BaseModel):
    type: Literal[
        "message",
        "confirmation_required",
        "disambiguation_required",
        "error",
    ] = "message"
    text: str = ""
    tool_calls: list[ToolCallLog] = Field(default_factory=list)
    # populated for confirmation / disambiguation
    action: str | None = None
    details: dict | None = None
    candidates: list[dict] | None = None
    error_code: str | None = None
    language: str | None = None
