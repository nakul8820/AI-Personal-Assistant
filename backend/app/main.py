import logging
import logging.config
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth_routes, chat_routes, debug_routes, voice_routes
from app.core.config import get_settings
from app.core.errors import AppError, SessionTimedOut

# Force unbuffered line-by-line output to sys.stdout for Render / Docker live logs
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

settings = get_settings()


def setup_logging():
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
                "stream": "ext://sys.stdout",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["console"]},
        "loggers": {
            "app":            {"level": "INFO", "propagate": True},
            "api.chat":       {"level": "INFO", "propagate": True},
            "api.voice":      {"level": "INFO", "propagate": True},
            "api.auth":       {"level": "INFO", "propagate": True},
            "llm.groq":       {"level": "INFO", "propagate": True},
            "llm.openrouter": {"level": "INFO", "propagate": True},
            "llm.prompt":     {"level": "INFO", "propagate": True},
            "llm.orchestrator": {"level": "INFO", "propagate": True},
            "tools.calendar": {"level": "INFO", "propagate": True},
            "tools.tasks":    {"level": "INFO", "propagate": True},
            "tools.contacts": {"level": "INFO", "propagate": True},
            "auth":           {"level": "INFO", "propagate": True},
            "db":             {"level": "INFO", "propagate": True},
            "memory.store":   {"level": "INFO", "propagate": True},
            "voice.sarvam":   {"level": "INFO", "propagate": True},
        },
    })


setup_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Re-apply logging after Uvicorn server startup to guarantee Uvicorn doesn't suppress logs
    setup_logging()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    logger.info(
        "Application startup complete | provider=%s | openrouter_fallback=%s",
        settings.llm_provider,
        "enabled" if settings.openrouter_api_key else "disabled",
    )
    yield


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="AI Personal Assistant", lifespan=lifespan)

# Build list of origins from config + production defaults
allowed_origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
for default_origin in ["http://localhost:3000", "https://ai-personal-assistant-chi.vercel.app"]:
    if default_origin not in allowed_origins:
        allowed_origins.append(default_origin)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="none",
    https_only=True,
    max_age=settings.session_max_age_hours * 3600,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app|https://.*\.ngrok-free\.app|https://.*\.ngrok-free\.dev|http://localhost:\d+",
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
