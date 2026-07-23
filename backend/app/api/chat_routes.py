import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import current_user
from app.llm import orchestrator, session
from app.memory.store import get_today_actions, get_history_for_ui, _today
from app.models.schemas import ChatRequest

logger = logging.getLogger("api.chat")
router = APIRouter(tags=["chat"])


def _tz(request: Request) -> str:
    tz_val = request.headers.get("X-User-Timezone", "UTC")
    logger.debug("Request header X-User-Timezone: %s", tz_val)
    return tz_val


@router.post("/chat")
def chat(req: ChatRequest, request: Request, user_id: str = Depends(current_user)):
    """Non-streaming: run the turn, return the final response + tool-call trace."""
    tz = _tz(request)
    session_id = session.make_session_id(user_id, tz)
    cs = session.get_or_create(session_id, user_id, tz)
    initial_history_len = len(cs.history)
    logger.info("Sync chat turn | user=%s tz=%s | message=%r", user_id, tz, req.message)

    final = None
    tool_calls: list[dict] = []
    for event in orchestrator.run(cs, req.message, req.language):
        if event["kind"] == "tool":
            tool_calls.append(event)
        elif event["kind"] == "final":
            final = event["response"]

    cs.save_with_merge(initial_history_len)

    if final is None:
        final = {"type": "message", "text": "…"}
    final.setdefault("tool_calls", [])
    if not final["tool_calls"]:
        final["tool_calls"] = tool_calls
    final["language"] = req.language
    return final


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, request: Request, user_id: str = Depends(current_user)):
    """SSE: emit status/tool cards as the state machine progresses, then final."""
    tz = _tz(request)
    session_id = session.make_session_id(user_id, tz)
    cs = session.get_or_create(session_id, user_id, tz)
    initial_history_len = len(cs.history)

    logger.info("Stream turn start | user=%s tz=%s session=%s | message=%r", user_id, tz, session_id, req.message)

    def gen():
        for event in orchestrator.run(cs, req.message, req.language):
            payload = json.dumps(event)
            logger.debug("Emitting SSE event kind=%s | len=%d", event.get("kind"), len(payload))
            yield f"data: {payload}\n\n"
        cs.save_with_merge(initial_history_len)
        logger.info("Stream turn completed & saved | user=%s | turns=%d", user_id, len(cs.history))

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.get("/chat/history")
def chat_history(request: Request, user_id: str = Depends(current_user)):
    """Return today's conversation history for UI restoration on page load."""
    tz = _tz(request)
    date = _today(tz)
    items = get_history_for_ui(user_id, date)
    session_id = session.make_session_id(user_id, tz)
    logger.info("History fetch | user=%s tz=%s date=%s | items=%d", user_id, tz, date, len(items))
    return {"session_id": session_id, "date": date, "items": items}


@router.get("/chat/activity")
def chat_activity(request: Request, user_id: str = Depends(current_user)):
    """Return today's action log for the 'Today's activity' panel."""
    tz = _tz(request)
    date = _today(tz)
    actions = get_today_actions(user_id, date)
    logger.info("Activity fetch | user=%s tz=%s date=%s | actions=%d", user_id, tz, date, len(actions))
    return {"date": date, "actions": actions}
