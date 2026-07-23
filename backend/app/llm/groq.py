"""Thin Groq REST client. Uses OpenAI-compatible chat completions API.

On HTTP 429, raises RateLimitExhausted so the orchestrator can fall back to
OpenRouter instead of crashing the stream.
"""

import json
import logging
import time

import httpx

from app.core.config import get_settings
from app.core.errors import GoogleAPIError

logger = logging.getLogger("llm.groq")

_URL = "https://api.groq.com/openai/v1/chat/completions"


class RateLimitExhausted(GoogleAPIError):
    """Raised when Groq 429 persists after all retries."""
    pass


class ToolCallFailed(GoogleAPIError):
    """Raised when Groq 400 tool_use_failed — model generated invalid function call syntax.
    
    This happens with llama-3.1-8b-instant when conversation history is complex.
    The orchestrator should fall back to OpenRouter for this call.
    """
    pass


def generate(system_prompt: str, contents: list[dict], tools: list[dict]) -> dict:
    """Return model content dict formatted consistently with Gemini parts structure.

    Return format:
    {
        "parts": [
            {"text": "..."},
            {"functionCall": {"name": "...", "args": {...}}}
        ],
        "usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N},
        "provider": "groq"
    }
    """
    s = get_settings()
    if not s.groq_api_key:
        raise GoogleAPIError("GROQ_API_KEY is not configured in environment.")

    # Convert conversation contents (Gemini format) to OpenAI format
    messages = [{"role": "system", "content": system_prompt}]
    pending_tool_calls: list[dict] = []

    for turn_idx, msg in enumerate(contents):
        role = msg.get("role", "user")
        parts = msg.get("parts", [])

        if role == "model":
            if pending_tool_calls:
                for ptc in pending_tool_calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": ptc["id"],
                        "content": json.dumps({"status": "confirmation_requested"}),
                    })
                pending_tool_calls = []

            assistant_text = ""
            tool_calls = []
            turn_pending = []

            for call_idx, part in enumerate(parts):
                if "text" in part:
                    assistant_text += part["text"]
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    call_id = f"call_{fc['name']}_{turn_idx}_{call_idx}"
                    tool_calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": fc["name"],
                            "arguments": json.dumps(fc.get("args", {}))
                        }
                    })
                    turn_pending.append({"id": call_id, "name": fc["name"]})

            msg_obj: dict = {"role": "assistant"}
            if assistant_text:
                msg_obj["content"] = assistant_text
            if tool_calls:
                msg_obj["tool_calls"] = tool_calls
                if "content" not in msg_obj:
                    msg_obj["content"] = None
                pending_tool_calls = turn_pending
            messages.append(msg_obj)

        else:
            user_texts = []
            func_responses = []

            for part in parts:
                if "text" in part:
                    user_texts.append(part["text"])
                elif "functionResponse" in part:
                    func_responses.append(part["functionResponse"])

            if func_responses:
                for fr in func_responses:
                    fr_name = fr.get("name")
                    matched_id = None
                    for idx, ptc in enumerate(pending_tool_calls):
                        if ptc["name"] == fr_name:
                            matched_id = ptc["id"]
                            pending_tool_calls.pop(idx)
                            break
                    if not matched_id:
                        matched_id = f"call_{fr_name}_fallback"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": matched_id,
                        "content": json.dumps(fr.get("response", {}))
                    })

                if pending_tool_calls:
                    for ptc in pending_tool_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": ptc["id"],
                            "content": json.dumps({"status": "handled"}),
                        })
                    pending_tool_calls = []

            if user_texts:
                if pending_tool_calls:
                    for ptc in pending_tool_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": ptc["id"],
                            "content": json.dumps({"status": "confirmation_requested_from_user"}),
                        })
                    pending_tool_calls = []

                for ut in user_texts:
                    messages.append({"role": "user", "content": ut})

    if pending_tool_calls:
        for ptc in pending_tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": ptc["id"],
                "content": json.dumps({"status": "pending"}),
            })
        pending_tool_calls = []

    def _clean_schema(obj):
        if isinstance(obj, dict):
            return {
                k: v.lower() if k == "type" and isinstance(v, str) else _clean_schema(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_clean_schema(x) for x in obj]
        return obj

    # Convert tools (Gemini function declarations) to OpenAI tool format
    groq_tools = []
    for tool in tools:
        params = tool.get("parameters", {"type": "object", "properties": {}})
        groq_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": _clean_schema(params)
            }
        })

    payload = {
        "model": s.groq_model,
        "messages": messages,
        "tools": groq_tools if groq_tools else None,
        "tool_choice": "auto" if groq_tools else None,
        "temperature": 0.2,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    headers = {
        "Authorization": f"Bearer {s.groq_api_key}",
        "Content-Type": "application/json",
    }

    logger.info(
        "Groq request | model=%s | messages=%d | tools=%d",
        s.groq_model, len(messages), len(groq_tools)
    )

    for attempt in range(3):
        try:
            r = httpx.post(_URL, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            break
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < 2:
                wait = 2 * (attempt + 1)
                logger.warning(
                    "Groq 429 rate limit on attempt %d/%d — retrying in %ds",
                    attempt + 1, 3, wait
                )
                time.sleep(wait)
                continue
            if e.response.status_code == 429:
                logger.error("Groq 429 rate limit exhausted after 3 attempts — raising RateLimitExhausted")
                raise RateLimitExhausted(f"Groq rate limit exhausted: {e.response.text[:200]}")
            # 400 error = model configuration / syntax issues (e.g. tool calling not supported or bad syntax)
            # Treat this as a fallback trigger so OpenRouter can handle it
            if e.response.status_code == 400:
                try:
                    err_body = e.response.json()
                    err_msg = err_body.get("error", {}).get("message", e.response.text)
                    failed_gen = err_body.get("error", {}).get("failed_generation", "")
                except Exception:
                    err_msg = e.response.text
                    failed_gen = ""
                logger.warning(
                    "Groq 400 Bad Request (%s) — raising ToolCallFailed to trigger OpenRouter fallback",
                    err_msg[:120]
                )
                raise ToolCallFailed(
                    f"Groq bad request error: {err_msg[:120]}. "
                    f"Falling back to OpenRouter."
                )
            logger.error("Groq HTTP error %s: %s", e.response.status_code, e.response.text[:300])
            raise GoogleAPIError(f"Groq error {e.response.status_code}: {e.response.text[:200]}")
        except httpx.HTTPError as e:
            logger.error("Groq network error: %s", e)
            raise GoogleAPIError(f"Groq unreachable: {e}")

    data = r.json()
    logger.debug("Groq raw response: %s", json.dumps(data)[:500])

    choices = data.get("choices")
    if not choices:
        raise GoogleAPIError(f"Groq returned no choices: {data}")

    message = choices[0].get("message", {})
    parts_out = []

    text_content = message.get("content")
    if text_content:
        parts_out.append({"text": text_content})

    tool_calls = message.get("tool_calls", [])
    for tc in tool_calls:
        func = tc.get("function", {})
        try:
            args = json.loads(func.get("arguments", "{}"))
        except Exception:
            args = {}
        parts_out.append({
            "functionCall": {
                "name": func.get("name"),
                "args": args
            }
        })

    usage = data.get("usage", {})
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    tt = usage.get("total_tokens", 0)

    logger.info(
        "Groq response | model=%s | prompt_tokens=%d | completion_tokens=%d | total=%d | tool_calls=%d",
        s.groq_model, pt, ct, tt, len(tool_calls)
    )

    return {
        "role": "model",
        "parts": parts_out,
        "usage": {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": tt,
        },
        "provider": "groq",
    }
