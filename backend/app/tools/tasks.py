"""Google Tasks tool functions."""

import logging
from datetime import date, datetime, timezone

from app.core.errors import NotFoundError
from app.models.schemas import DeleteResult, TaskSummary, TaskUpdate
from app.tools._google import guarded, service

logger = logging.getLogger("tools.tasks")


def _svc(user_id: str):
    return service(user_id, "tasks", "v1")


def _default_list_id(user_id: str) -> str:
    res = _svc(user_id).tasklists().list(maxResults=1).execute()
    items = res.get("items", [])
    if not items:
        raise NotFoundError("No task lists found.")
    return items[0]["id"]


def _due_to_date(due: str | None) -> date | None:
    if not due:
        return None
    return datetime.fromisoformat(due.replace("Z", "+00:00")).date()


def _date_to_due(d: date | None) -> str | None:
    if not d:
        return None
    # Tasks API stores due as RFC3339 UTC; only the date part is honored.
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()


def _to_summary(t: dict, list_id: str) -> TaskSummary:
    return TaskSummary(
        id=t["id"],
        title=t.get("title", "(untitled)"),
        due=_due_to_date(t.get("due")),
        status=t.get("status", "needsAction"),
        task_list_id=list_id,
    )


@guarded
def list_tasks(
    user_id: str,
    task_list_id: str | None = None,
    due_range_start: date | None = None,
    due_range_end: date | None = None,
    status: str = "needsAction",
) -> list[TaskSummary]:
    logger.info("list_tasks | user=%s | status=%s | start=%s | end=%s", user_id, status, due_range_start, due_range_end)
    list_id = task_list_id or _default_list_id(user_id)
    kwargs: dict = {"tasklist": list_id, "maxResults": 100, "showCompleted": True}
    if status == "completed":
        kwargs["showHidden"] = True
    res = _svc(user_id).tasks().list(**kwargs).execute()
    out = []
    for t in res.get("items", []):
        summ = _to_summary(t, list_id)
        if status != "all" and summ.status != status:
            continue
        if due_range_start and (summ.due is None or summ.due < due_range_start):
            continue
        if due_range_end and (summ.due is None or summ.due > due_range_end):
            continue
        out.append(summ)
    logger.info("list_tasks found | count=%d", len(out))
    return out


@guarded
def create_task(
    user_id: str,
    title: str,
    due: date | None = None,
    notes: str | None = None,
    task_list_id: str | None = None,
) -> TaskSummary:
    logger.info("create_task | title=%r | due=%s", title, due)
    list_id = task_list_id or _default_list_id(user_id)
    body: dict = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = _date_to_due(due)
    t = _svc(user_id).tasks().insert(tasklist=list_id, body=body).execute()
    summary = _to_summary(t, list_id)
    logger.info("create_task created | id=%s", summary.id)
    return summary


@guarded
def update_task(
    user_id: str, task_id: str, updates: TaskUpdate, task_list_id: str | None = None
) -> TaskSummary:
    logger.info("update_task | id=%s", task_id)
    list_id = task_list_id or _default_list_id(user_id)
    body: dict = {}
    if updates.title is not None:
        body["title"] = updates.title
    if updates.notes is not None:
        body["notes"] = updates.notes
    if updates.status is not None:
        body["status"] = updates.status
    if updates.due is not None:
        body["due"] = _date_to_due(updates.due)
    if not body:
        raise NotFoundError("No fields to update.")
    t = (
        _svc(user_id)
        .tasks()
        .patch(tasklist=list_id, task=task_id, body=body)
        .execute()
    )
    return _to_summary(t, list_id)


@guarded
def complete_task(
    user_id: str, task_id: str, task_list_id: str | None = None
) -> TaskSummary:
    logger.info("complete_task | id=%s", task_id)
    return update_task(
        user_id, task_id, TaskUpdate(status="completed"), task_list_id
    )


@guarded
def delete_task(
    user_id: str, task_id: str, task_list_id: str | None = None
) -> DeleteResult:
    logger.info("delete_task | id=%s", task_id)
    list_id = task_list_id or _default_list_id(user_id)
    _svc(user_id).tasks().delete(tasklist=list_id, task=task_id).execute()
    return DeleteResult(id=task_id)
