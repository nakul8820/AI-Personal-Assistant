"""Thin OpenRouter REST client. Uses OpenAI-compatible chat completions API.

OpenRouter is used as the fallback provider when Groq is rate-limited (429).
It supports the same OpenAI-wire format, so this file mirrors groq.py closely.
"""

import json
import logging

import httpx

from app.core.config import get_settings
from app.core.errors import GoogleAPIError

logger = logging.getLogger("llm.openrouter")

_URL = "https://openrouter.ai/api/v1/chat/completions"


def generate(system_prompt: str, contents: list[dict], tools: list[dict]) -> dict:
    """Return model content dict formatted consistently with Gemini parts structure.

    Return format:
    {
        "parts": [
            {"text": "..."},
            {"functionCall": {"name": "...", "args": {...}}}
        ],
        "usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N},
        "provider": "openrouter"
    }
    """
    s = get_settings()
    if not s.openrouter_api_key:
        raise GoogleAPIError("OPENROUTER_API_KEY is not configured in environment.")

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

    # Convert tools to OpenAI tool format
    openrouter_tools = []
    for tool in tools:
        params = tool.get("parameters", {"type": "object", "properties": {}})
        openrouter_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": _clean_schema(params)
            }
        })

    payload = {
        "model": s.openrouter_model,
        "messages": messages,
        "tools": openrouter_tools if openrouter_tools else None,
        "tool_choice": "auto" if openrouter_tools else None,
        "temperature": 0.2,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    headers = {
        "Authorization": f"Bearer {s.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ai-personal-assistant.local",
        "X-Title": "AI Personal Assistant",
    }

    logger.info(
        "OpenRouter request | model=%s | messages=%d | tools=%d",
        s.openrouter_model, len(messages), len(openrouter_tools)
    )

    try:
        r = httpx.post(_URL, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("OpenRouter HTTP error %s: %s", e.response.status_code, e.response.text[:300])
        raise GoogleAPIError(f"OpenRouter error {e.response.status_code}: {e.response.text[:200]}")
    except httpx.HTTPError as e:
        logger.error("OpenRouter network error: %s", e)
        raise GoogleAPIError(f"OpenRouter unreachable: {e}")

    data = r.json()
    logger.debug("OpenRouter raw response: %s", json.dumps(data)[:500])

    choices = data.get("choices")
    if not choices:
        raise GoogleAPIError(f"OpenRouter returned no choices: {data}")

    message = choices[0].get("message", {})
    parts_out = []

    text_content = message.get("content")
    if text_content:
        parts_out.append({"text": text_content})

    tool_calls_resp = message.get("tool_calls", [])
    for tc in tool_calls_resp:
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
        "OpenRouter response | model=%s | prompt_tokens=%d | completion_tokens=%d | total=%d | tool_calls=%d",
        s.openrouter_model, pt, ct, tt, len(tool_calls_resp)
    )

    return {
        "role": "model",
        "parts": parts_out,
        "usage": {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": tt,
        },
        "provider": "openrouter",
    }
