"""Shared plumbing: build discovery services, translate + retry Google errors."""

import time
from functools import wraps

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.auth.google_oauth import credentials_for
from app.core.errors import (
    GoogleAPIError,
    GoogleAuthError,
    GoogleRateLimitError,
    NotFoundError,
)

_MAX_RETRIES = 3


def service(user_id: str, name: str, version: str):
    return build(
        name, version, credentials=credentials_for(user_id), cache_discovery=False
    )


def guarded(fn):
    """Translate HttpError -> typed errors; exp-backoff up to 3x on 429."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        attempt = 0
        while True:
            try:
                return fn(*args, **kwargs)
            except HttpError as e:
                status = getattr(e.resp, "status", None)
                status = int(status) if status is not None else None

                # Extract raw error message for better diagnostics
                error_details = ""
                try:
                    import json
                    content = json.loads(e.content.decode("utf-8"))
                    error_details = content.get("error", {}).get("message", "")
                except Exception:
                    error_details = str(e)

                # Check if the API itself is disabled in Google Cloud Console
                is_disabled_api = (
                    "disabled" in error_details.lower()
                    or "accessnotconfigured" in error_details.lower()
                    or "not been used" in error_details.lower()
                )

                if status == 429 and attempt < _MAX_RETRIES:
                    time.sleep(2**attempt)  # 1s, 2s, 4s
                    attempt += 1
                    continue
                if status == 429:
                    raise GoogleRateLimitError("Google is rate-limiting; try shortly.")
                if is_disabled_api:
                    raise GoogleAPIError(
                        f"Google API is disabled in your Cloud Console project. "
                        f"Please enable it: {error_details}"
                    )
                if status in (401, 403):
                    raise GoogleAuthError("Google connection needs renewal.")
                if status == 404:
                    raise NotFoundError("The requested item was not found.")
                raise GoogleAPIError(f"Google API error ({status}): {error_details}") from e

    return wrapper
