import logging
import logging.config

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth_routes, chat_routes, debug_routes, voice_routes
from app.core.config import get_settings
from app.core.errors import AppError, SessionTimedOut

settings = get_settings()

# ── Structured logging setup ─────────────────────────────────────────────────
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        # LLM layer — set to DEBUG to see raw request/response payloads
        "llm.groq":       {"level": "INFO", "propagate": True},
        "llm.openrouter": {"level": "INFO", "propagate": True},
        "llm.orchestrator": {"level": "INFO", "propagate": True},
        # Auth layer
        "auth":           {"level": "INFO", "propagate": True},
    },
})

logger = logging.getLogger("app")
logger.info(
    "Starting AI Personal Assistant | provider=%s | openrouter_fallback=%s | session_max_age=%dh",
    settings.llm_provider,
    "enabled" if settings.openrouter_api_key else "disabled (no OPENROUTER_API_KEY)",
    settings.session_max_age_hours,
)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="AI Personal Assistant")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="none",
    https_only=True,
    max_age=settings.session_max_age_hours * 3600,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SessionTimedOut)
def session_timeout_handler(_request: Request, exc: SessionTimedOut):
    """Idle timeout -> 401 with SESSION_TIMEOUT code so frontend shows lock overlay."""
    logger.warning("SessionTimedOut: %s", exc.message)
    return JSONResponse(
        {"error_code": "SESSION_TIMEOUT", "message": exc.message},
        status_code=401,
    )


@app.exception_handler(AppError)
def app_error_handler(_request: Request, exc: AppError):
    """Typed errors -> clean JSON. No stack traces to clients."""
    logger.warning("AppError: code=%s message=%s", exc.code, exc.message)
    return JSONResponse(
        {"error_code": exc.code, "message": exc.message},
        status_code=exc.http_status,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(voice_routes.router)
if settings.enable_debug_routes:
    app.include_router(debug_routes.router)
