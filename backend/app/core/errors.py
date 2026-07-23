"""Typed exceptions. Raw google/httpx errors must never leak past the tool layer."""


class AppError(Exception):
    """Base. `code` is the stable string the API/frontend switches on."""

    code = "APP_ERROR"
    http_status = 500

    def __init__(self, message: str | None = None):
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__


class NotFoundError(AppError):
    code = "NOT_FOUND"
    http_status = 404


class AmbiguousResultError(AppError):
    code = "AMBIGUOUS_RESULT"
    http_status = 409


class GoogleAuthError(AppError):
    code = "AUTH_EXPIRED"
    http_status = 401


class GoogleRateLimitError(AppError):
    code = "RATE_LIMITED"
    http_status = 429


class GoogleAPIError(AppError):
    code = "GOOGLE_API_ERROR"
    http_status = 502


class VoiceServiceError(AppError):
    code = "VOICE_UNAVAILABLE"
    http_status = 502


class SessionTimedOut(AppError):
    """Raised when the user has been idle longer than idle_timeout_minutes."""
    code = "SESSION_TIMEOUT"
    http_status = 401


class SessionConflictError(AppError):
    """Raised when optimistic concurrency check fails on day_sessions write."""
    code = "SESSION_CONFLICT"
    http_status = 409

