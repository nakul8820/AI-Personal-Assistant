"""State machine + multi-provider LLM loop + the backend safety interceptor.

`run()` is a generator yielding progress events; the final event carries the
terminal ChatResponse dict. The /chat route can stream events (SSE) or collect
them (JSON) — same source of truth either way.

Provider routing strategy:
  1. Primary: Groq (fast, free, supports function calling)
  2. Fallback: OpenRouter (activates only when Groq 429 is exhausted)

Non-negotiable invariant: delete_calendar_event / delete_task / complete_task
NEVER execute unless they came out of a confirmed pending_action. This is
enforced here in code, independent of anything the LLM outputs.
"""

import logging
from datetime import datetime

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    GoogleAuthError,
    GoogleAPIError,
    GoogleRateLimitError,
)
from app.llm import gemini, groq, intent, openrouter
from app.llm.groq import RateLimitExhausted, ToolCallFailed
from app.llm.prompt import build_system_prompt
from app.llm.session import ConversationState, State
from app.memory.store import log_action, _today
from app.tools.registry import DESTRUCTIVE, SEARCH, dispatch

logger = logging.getLogger("llm.orchestrator")

MAX_ROUNDTRIPS = 6

_STATUS = {
    "search_calendar_events": "🔍 Searching your calendar…",
    "create_calendar_event": "📅 Creating the event…",
    "update_calendar_event": "✏️ Updating the event…",
    "delete_calendar_event": "🗑️ Deleting the event…",
    "list_tasks": "🔍 Checking your tasks…",
    "create_task": "➕ Adding the task…",
    "update_task": "✏️ Updating the task…",
    "complete_task": "✅ Completing the task…",
    "delete_task": "🗑️ Deleting the task…",
    "search_contacts": "👤 Looking up the contact…",
}


# ---------- small helpers ----------


def _text_content(role: str, text: str) -> dict:
    return {"role": role, "parts": [{"text": text}]}


def _fn_response(name: str, result: dict) -> dict:
    return {"role": "user", "parts": [{"functionResponse": {"name": name, "response": result}}]}


def _fmt_when(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%a %d %b, %-I:%M %p")
    except Exception:
        return iso


def _event_details(ev: dict) -> dict:
    return {
        "kind": "event",
        "id": ev["id"],
        "title": ev.get("title", "(event)"),
        "when": _fmt_when(ev.get("start")),
        "recurring_event_id": ev.get("recurring_event_id"),
    }


def _task_details(t: dict) -> dict:
    return {
        "kind": "task",
        "id": t["id"],
        "title": t.get("title", "(task)"),
        "when": str(t.get("due") or ""),
    }


def _final(**kw) -> dict:
    base = {
        "type": "message",
        "text": "",
        "tool_calls": [],
        "action": None,
        "details": None,
        "candidates": None,
        "error_code": None,
    }
    base.update(kw)
    return {"kind": "final", "response": base}


# ---------- resumption: user is answering a pending prompt ----------


def _resume(cs: ConversationState, message: str):
    action = cs.pending_action
    cs.history.append(_text_content("user", message))

    # recurring scope first
    if action.get("needs_scope"):
        scope = intent.parse_scope(message)
        if scope is None:
            yield _final(
                type="confirmation_required",
                action="recurring_scope",
                details=action["details"],
                text="Please choose: this occurrence, this and following, or the entire series?",
            )
            return
        # occurrence -> use the occurrence id; all/following -> series id
        # ponytail: 'following' is applied to the series (Google needs an RRULE
        # split for a true this-and-following; documented limitation).
        rec = action["recurring"]
        target_id = rec["occurrence_id"] if scope == "occurrence" else rec["series_id"]
        action["args"]["event_id"] = target_id
        action["details"]["scope"] = scope
        action["needs_scope"] = False

    # destructive still needs yes/no
    if action.get("needs_confirm"):
        ans = intent.is_affirmative(message)
        if ans is None:
            yield _final(
                type="confirmation_required",
                action=action["name"],
                details=action["details"],
                text="Sorry, was that a yes or a no?",
            )
            return
        if ans is False:
            cs.pending_action = None
            cs.state = State.AWAITING_INPUT
            yield _final(text="Okay, cancelled — nothing was changed.")
            return
        action["needs_confirm"] = False

    # everything cleared -> execute
    yield from _execute_pending(cs)


def _execute_pending(cs: ConversationState):
    action = cs.pending_action
    name, args, details = action["name"], action["args"], action["details"]
    yield {"kind": "status", "text": _STATUS.get(name, "Working…")}
    try:
        dispatch(cs.user_id, name, args)
    except (GoogleAuthError, GoogleRateLimitError) as e:
        cs.pending_action = None
        cs.state = State.AWAITING_INPUT
        yield _final(type="error", error_code=e.code, text=_friendly(e))
        return
    except AppError as e:
        cs.pending_action = None
        cs.state = State.AWAITING_INPUT
        yield _final(type="error", error_code=e.code, text=e.message)
        return
    cs.pending_action = None
    cs.state = State.AWAITING_INPUT
    verb = {
        "delete_calendar_event": "Deleted",
        "delete_task": "Deleted",
        "complete_task": "Completed",
    }.get(name, "Done —")
    when = f" ({details['when']})" if details.get("when") else ""
    yield _final(
        text=f"{verb} “{details['title']}”{when}.",
        tool_calls=[{"name": name, "arguments": args, "result_summary": "ok"}],
    )


# ---------- main turn ----------


def _friendly(e: AppError) -> str:
    if e.code == "AUTH_EXPIRED":
        return "Your Google connection needs renewing — please reconnect your account."
    if e.code == "RATE_LIMITED":
        return "Google is briefly unreachable (rate limited). Want me to retry in a moment?"
    return e.message


def run(cs: ConversationState, message: str, language: str | None = None):
    """Yield progress events; last event is {'kind':'final', 'response': {...}}."""
    # Resume a pending confirmation/scope prompt (backend-owned, not the LLM).
    if cs.pending_action:
        yield from _resume(cs, message)
        return

    cs.state = State.AWAITING_INPUT
    lang_hint = f"\n[Detected input language: {language}]" if language else ""
    cs.history.append(_text_content("user", message + lang_hint))
    system_prompt = build_system_prompt(cs.user_timezone)
    current_message = message  # stored for action_log

    known = cs.known_items            # id -> details, conversation-scoped
    last_candidates: list[dict] = []   # for disambiguation surfacing (this turn)
    tool_logs: list[dict] = []

    settings = get_settings()
    primary_llm = groq if settings.llm_provider == "groq" else gemini
    has_fallback = bool(settings.openrouter_api_key)

    hit_count = 0
    total_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0
    providers_used: list[str] = []

    logger.info(
        "Turn start | user=%s | session=%s | primary=%s | fallback=%s",
        cs.user_id, cs.session_id if hasattr(cs, 'session_id') else 'n/a',
        settings.llm_provider,
        f"openrouter({settings.openrouter_model})" if has_fallback else "none"
    )

    for round_num in range(MAX_ROUNDTRIPS):
        hit_count += 1
        logger.info("LLM hit #%d | history_len=%d", hit_count, len(cs.history))

        # ── 3-Stage Fallback Chain: Groq → OpenRouter → Gemini ────────────────
        content = None
        errors = []

        # Stage 1: Groq
        try:
            content = groq.generate(system_prompt, cs.llm_history(), _declarations())
            providers_used.append("groq")
        except Exception as e:
            logger.warning("Groq failed on hit #%d: %s", hit_count, e)
            errors.append(f"Groq error: {str(e)[:80]}")

            # Stage 2: OpenRouter
            if settings.openrouter_api_key:
                logger.info("Falling back to OpenRouter (%s)", settings.openrouter_model)
                try:
                    content = openrouter.generate(system_prompt, cs.llm_history(), _declarations())
                    providers_used.append("openrouter")
                except Exception as oe:
                    logger.warning("OpenRouter fallback failed: %s", oe)
                    errors.append(f"OpenRouter error: {str(oe)[:80]}")
            else:
                errors.append("OpenRouter not configured (no key)")

            # Stage 3: Gemini (only if content is still None)
            if content is None:
                if settings.gemini_api_key:
                    logger.info("Falling back to Gemini (%s)", settings.gemini_model)
                    try:
                        content = gemini.generate(system_prompt, cs.llm_history(), _declarations())
                        content["provider"] = "gemini"
                        content["role"] = "model"
                        providers_used.append("gemini")
                    except Exception as ge:
                        logger.error("Gemini fallback also failed: %s", ge)
                        errors.append(f"Gemini error: {str(ge)[:80]}")
                else:
                    errors.append("Gemini not configured (no key)")

        if content is None:
            err_summary = " | ".join(errors)
            yield _final(
                type="error",
                error_code="RATE_LIMITED",
                text=f"All LLM providers (Groq, OpenRouter, Gemini) failed to respond. Errors: {err_summary}",
                tool_calls=tool_logs,
            )
            return

        usage = content.get("usage", {})
        hit_pt = usage.get("prompt_tokens", 0)
        hit_ct = usage.get("completion_tokens", 0)
        hit_tt = usage.get("total_tokens", 0)
        prompt_tokens += hit_pt
        completion_tokens += hit_ct
        total_tokens += hit_tt

        logger.info(
            "Hit #%d done | provider=%s | prompt_tok=%d | completion_tok=%d | total_tok=%d (cumulative=%d)",
            hit_count, providers_used[-1], hit_pt, hit_ct, hit_tt, total_tokens
        )

        metrics = {
            "api_hits": hit_count,
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model": settings.groq_model if settings.llm_provider == "groq" else settings.gemini_model,
            "providers_used": " → ".join(providers_used),
        }

        calls = gemini.extract_calls(content)
        logger.info("Hit #%d | tool_calls=%d | has_text=%s", hit_count, len(calls), bool(gemini.extract_text(content)))

        if not calls:
            text = gemini.extract_text(content) or "…"
            cs.history.append(content)
            logger.info("Turn complete | total_hits=%d | total_tokens=%d | providers=%s",
                        hit_count, total_tokens, metrics["providers_used"])
            # surface tappable candidates if the model is asking to disambiguate
            if len(last_candidates) > 1 and text.rstrip().endswith("?"):
                cs.state = State.AWAITING_DISAMBIGUATION
                cs.pending_candidates = last_candidates
                yield _final(
                    type="disambiguation_required",
                    text=text,
                    candidates=last_candidates[:5],
                    tool_calls=tool_logs,
                    metrics=metrics,
                )
                return
            yield _final(text=text, tool_calls=tool_logs, metrics=metrics)
            return

        cs.history.append(content)  # model turn with functionCall(s)

        for call in calls:
            name, args = call["name"], call["args"]

            # ---- INTERCEPT: destructive or recurring-scoped mutations ----
            gate = _needs_gate(name, args, known)
            if gate:
                cs.pending_action = gate
                cs.state = State.AWAITING_CONFIRMATION
                if gate.get("needs_scope"):
                    yield _final(
                        type="confirmation_required",
                        action="recurring_scope",
                        details=gate["details"],
                        text="That's a recurring event. Apply to: this occurrence, this and following, or the entire series?",
                        tool_calls=tool_logs,
                    )
                else:
                    d = gate["details"]
                    when = f" on {d['when']}" if d.get("when") else ""
                    yield _final(
                        type="confirmation_required",
                        action=name,
                        details=d,
                        text=f"Delete “{d['title']}”{when}? (yes/no)",
                        tool_calls=tool_logs,
                    )
                return

            # ---- normal execution ----
            yield {"kind": "status", "text": _STATUS.get(name, "Working…")}
            try:
                result = dispatch(
                    cs.user_id,
                    name,
                    args,
                    tz_str=cs.user_timezone if hasattr(cs, "user_timezone") else "UTC"
                )
            except (GoogleAuthError, GoogleRateLimitError) as e:
                yield _final(type="error", error_code=e.code, text=_friendly(e), tool_calls=tool_logs)
                return
            except AppError as e:
                # let the model explain no-result / not-found gracefully
                result = {"error": e.code, "message": e.message}
                tool_logs.append({"name": name, "arguments": args, "error": e.code})
                cs.history.append(_fn_response(name, result))
                yield {"kind": "tool", "name": name, "arguments": args, "error": e.code}
                continue

            _index(name, result, known, last_candidates)
            summary = _summarize(name, result)
            tool_logs.append({"name": name, "arguments": args, "result_summary": summary})
            cs.history.append(_fn_response(name, result))
            # Persist to action_log for "Today's activity" panel
            log_action(
                user_id=cs.user_id,
                date=cs.date if hasattr(cs, "date") else _today(cs.user_timezone),
                user_message=current_message,
                tool_name=name,
                tool_args=args,
                result_summary=summary,
                provider=providers_used[-1] if providers_used else settings.llm_provider,
                api_hits=hit_count,
                total_tokens=total_tokens,
            )
            yield {"kind": "tool", "name": name, "arguments": args,
                   "result_summary": summary}

    # loop cap hit
    yield _final(text="I'm having trouble completing this — could you rephrase?", tool_calls=tool_logs)


# ---------- interceptor + indexing ----------


def _needs_gate(name: str, args: dict, known: dict) -> dict | None:
    """Return a pending_action dict if this call must pause; else None."""
    is_destructive = name in DESTRUCTIVE
    is_cal_mutation = name in ("update_calendar_event", "delete_calendar_event")

    target = None
    if name in ("delete_calendar_event", "update_calendar_event"):
        target = known.get(args.get("event_id"))
    elif name in ("delete_task", "complete_task"):
        target = known.get(args.get("task_id"))

    recurring = None
    if is_cal_mutation and target and target.get("recurring_event_id"):
        recurring = {
            "occurrence_id": target["id"],
            "series_id": target["recurring_event_id"],
        }

    if not is_destructive and not recurring:
        return None

    details = target or {"title": "this item", "when": ""}
    return {
        "name": name,
        "args": dict(args),
        "details": dict(details),
        "needs_scope": bool(recurring),
        "needs_confirm": is_destructive,
        "recurring": recurring,
    }


def _index(name: str, result: dict, known: dict, last_candidates: list) -> None:
    if name == "search_calendar_events":
        last_candidates.clear()
        for ev in result.get("events", []):
            d = _event_details(ev)
            known[ev["id"]] = d
            last_candidates.append(d)
    elif name == "list_tasks":
        last_candidates.clear()
        for t in result.get("tasks", []):
            d = _task_details(t)
            known[t["id"]] = d
            last_candidates.append(d)
    elif name == "search_contacts":
        last_candidates.clear()
        for c in result.get("contacts", []):
            last_candidates.append({"title": c["name"], "when": c["email"]})
    elif name == "create_calendar_event":
        ev = result.get("event", {})
        if ev.get("id"):
            known[ev["id"]] = _event_details(ev)


def _summarize(name: str, result: dict) -> str:
    if "events" in result:
        return f"{len(result['events'])} event(s)"
    if "tasks" in result:
        return f"{len(result['tasks'])} task(s)"
    if "contacts" in result:
        return f"{len(result['contacts'])} contact(s)"
    if "event" in result:
        return result["event"].get("title", "event")
    if "task" in result:
        return result["task"].get("title", "task")
    return "ok"


def _declarations():
    from app.tools.registry import DECLARATIONS
    return DECLARATIONS


# expose for callers/tests
__all__ = ["run", "MAX_ROUNDTRIPS", "SEARCH"]
