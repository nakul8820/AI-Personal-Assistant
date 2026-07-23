"""Manual tool testing (Sprint 1). Remove/disable in production."""

from datetime import date, datetime

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.models.schemas import CalendarEventUpdate, TaskUpdate
from app.tools import calendar, contacts, tasks

router = APIRouter(prefix="/debug/tools", tags=["debug"])


@router.get("/calendar/search")
def d_search(query: str, start: datetime, end: datetime, user_id: str = Depends(current_user)):
    return calendar.search_calendar_events(user_id, query, start, end)


@router.post("/calendar/create")
def d_create(title: str, start: datetime, end: datetime, user_id: str = Depends(current_user)):
    return calendar.create_calendar_event(user_id, title, start, end)


@router.post("/calendar/update")
def d_update(event_id: str, updates: CalendarEventUpdate, user_id: str = Depends(current_user)):
    return calendar.update_calendar_event(user_id, event_id, updates)


@router.delete("/calendar/{event_id}")
def d_delete(event_id: str, user_id: str = Depends(current_user)):
    return calendar.delete_calendar_event(user_id, event_id)


@router.get("/tasks/list")
def d_tasks(status: str = "needsAction", user_id: str = Depends(current_user)):
    return tasks.list_tasks(user_id, status=status)


@router.post("/tasks/create")
def d_task_create(title: str, due: date | None = None, user_id: str = Depends(current_user)):
    return tasks.create_task(user_id, title, due=due)


@router.post("/tasks/update")
def d_task_update(task_id: str, updates: TaskUpdate, user_id: str = Depends(current_user)):
    return tasks.update_task(user_id, task_id, updates)


@router.post("/tasks/{task_id}/complete")
def d_task_complete(task_id: str, user_id: str = Depends(current_user)):
    return tasks.complete_task(user_id, task_id)


@router.delete("/tasks/{task_id}")
def d_task_delete(task_id: str, user_id: str = Depends(current_user)):
    return tasks.delete_task(user_id, task_id)


@router.get("/contacts/search")
def d_contacts(name: str, user_id: str = Depends(current_user)):
    return contacts.search_contacts(user_id, name)
