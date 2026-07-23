import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import google_oauth, store
from app.core.config import get_settings
from app.core.errors import GoogleAuthError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request):
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    referer = request.headers.get("referer")
    if referer:
        request.session["login_referer"] = referer
    url = google_oauth.authorization_url(state)
    return RedirectResponse(url)


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None):
    if not code or not state:
        return JSONResponse({"error": "INVALID_OAUTH_PARAMS"}, status_code=400)
    # Check session state if present (lenient for cross-domain browser cookie policies)
    session_state = request.session.get("oauth_state")
    if session_state and state != session_state:
        return JSONResponse({"error": "INVALID_OAUTH_STATE"}, status_code=400)
        
    user_id, email = google_oauth.exchange_code(code, state)
    settings = get_settings()
    if settings.allowed_user_emails and email not in settings.allowed_user_emails:
        store.delete(user_id)
        return JSONResponse(
            {"error": "UNAUTHORIZED_USER", "message": f"User {email} is not authorized to access this assistant."},
            status_code=403,
        )
    request.session["user_id"] = user_id
    request.session.pop("oauth_state", None)
    redirect_url = request.session.pop("login_referer", settings.frontend_origin)
    return RedirectResponse(redirect_url)


@router.get("/status")
def status(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return {"authenticated": False}
    # Touch active timestamp since status check is active usage
    store.touch_active(user_id)
    try:
        google_oauth.credentials_for(user_id)  # triggers refresh if needed
    except GoogleAuthError:
        return {"authenticated": False, "error_code": "AUTH_EXPIRED", "email": store.email_for(user_id)}
        
    name = None
    try:
        creds_data = store.load(user_id)
        if creds_data:
            name = creds_data.get("user_name")
    except Exception:
        pass
        
    if not name:
        email = store.email_for(user_id)
        if email:
            parts = email.split("@")[0].split(".")
            name_parts = []
            for p in parts:
                cleaned = ''.join([c for c in p if not c.isdigit()])
                if cleaned:
                    name_parts.append(cleaned.title())
            name = " ".join(name_parts)
            
    return {"authenticated": True, "email": store.email_for(user_id), "name": name}


@router.post("/logout")
def logout(request: Request):
    user_id = request.session.pop("user_id", None)
    if user_id:
        store.delete(user_id)
    return {"ok": True}
