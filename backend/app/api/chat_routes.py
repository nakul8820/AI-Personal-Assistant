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
    return request.headers.get("X-User-Timezone", "UTC")


@router.post("/chat")
def chat(req: ChatRequest, request: Request, user_id: str = Depends(current_user)):
    """Non-streaming: run the turn, return the final response + tool-call trace."""
    tz = _tz(request)
    session_id = session.make_session_id(user_id, tz)
    cs = session.get_or_create(session_id, user_id, tz)

    final = None
    tool_calls: list[dict] = []
    for event in orchestrator.run(cs, req.message, req.language):
        if event["kind"] == "tool":
            tool_calls.append(event)
        elif event["kind"] == "final":
            final = event["response"]

    cs.save()

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
    # Always use stable day-scoped session key — ignore any client-supplied session_id
    session_id = session.make_session_id(user_id, tz)
    cs = session.get_or_create(session_id, user_id, tz)

    logger.info("Chat turn | user=%s session=%s | message_len=%d", user_id, session_id, len(req.message))

    def gen():
        for event in orchestrator.run(cs, req.message, req.language):
            yield f"data: {json.dumps(event)}\n\n"
        # Save state after generator exhausts
        cs.save()
        logger.info("Session saved | user=%s | turns=%d", user_id, len(cs.history))

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    )


@router.get("/chat/history")
def chat_history(request: Request, user_id: str = Depends(current_user)):
    """Return today's conversation history for UI restoration on page load."""
    tz = _tz(request)
    date = _today(tz)
    items = get_history_for_ui(user_id, date)
    session_id = session.make_session_id(user_id, tz)
    logger.info("History fetch | user=%s date=%s | items=%d", user_id, date, len(items))
    return {"session_id": session_id, "date": date, "items": items}


@router.get("/chat/activity")
def chat_activity(request: Request, user_id: str = Depends(current_user)):
    """Return today's action log for the 'Today's activity' panel."""
    tz = _tz(request)
    date = _today(tz)
    actions = get_today_actions(user_id, date)
    return {"date": date, "actions": actions}
