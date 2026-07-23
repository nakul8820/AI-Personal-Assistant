"""Thin Gemini REST client. No SDK -> no version drift; the JSON format is stable."""

import httpx

from app.core.config import get_settings
from app.core.errors import GoogleAPIError

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def generate(system_prompt: str, contents: list[dict], tools: list[dict]) -> dict:
    """Return the model's content (dict with `parts`). Raises GoogleAPIError."""
    s = get_settings()
    url = f"{_BASE}/{s.gemini_model}:generateContent"

    # Clean contents for Gemini REST API: strip non-standard keys like usage, provider, metrics
    clean_contents = []
    for item in contents:
        clean_contents.append({
            "role": item.get("role", "user"),
            "parts": item.get("parts", []),
        })

    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": clean_contents,
        "tools": [{"function_declarations": tools}],
        "tool_config": {"function_calling_config": {"mode": "AUTO"}},
    }
    try:
        r = httpx.post(
            url,
            params={"key": s.gemini_api_key},
            json=body,
            timeout=60,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise GoogleAPIError(f"Gemini error {e.response.status_code}: {e.response.text[:200]}")
    except httpx.HTTPError as e:
        raise GoogleAPIError(f"Gemini unreachable: {e}")

    data = r.json()
    candidates = data.get("candidates")
    if not candidates:
        raise GoogleAPIError(f"Gemini returned no candidates: {data}")
    return candidates[0].get("content", {"parts": []})


def extract_calls(content: dict) -> list[dict]:
    """Return [{'name':..., 'args':...}, ...] from a model content block."""
    calls = []
    for part in content.get("parts", []):
        fc = part.get("functionCall")
        if fc:
            calls.append({"name": fc["name"], "args": fc.get("args", {})})
    return calls


def extract_text(content: dict) -> str:
    return "".join(
        part["text"] for part in content.get("parts", []) if "text" in part
    ).strip()
