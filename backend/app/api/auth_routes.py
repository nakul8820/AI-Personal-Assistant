import base64
import json
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api import deps
from app.auth import google_oauth, store
from app.core.config import get_settings
from app.core.errors import GoogleAuthError

router = APIRouter(prefix="/auth", tags=["auth"])


def _encode_state(target_url: str) -> str:
    payload = {
        "nonce": secrets.token_urlsafe(16),
        "redirect": target_url,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_state(state: str) -> str | None:
    try:
        data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        if isinstance(data, dict):
            return data.get("redirect")
    except Exception:
        pass
    return None


@router.get("/login")
def login(request: Request, redirect: str | None = None):
    settings = get_settings()
    raw_target = redirect or request.headers.get("referer") or settings.frontend_origin
    # Strip any trailing auth_token query params
    clean_target = raw_target.split("?auth_token=")[0].split("&auth_token=")[0]
    
    state = _encode_state(clean_target)
    request.session["oauth_state"] = state
    url = google_oauth.authorization_url(state)
    return RedirectResponse(url)


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None):
    if not code or not state:
        return JSONResponse({"error": "INVALID_OAUTH_PARAMS"}, status_code=400)

    settings = get_settings()
    base_redirect = _decode_state(state) or request.session.pop("login_referer", settings.frontend_origin)
    
    user_id, email = google_oauth.exchange_code(code, state)
    if settings.allowed_user_emails and email not in settings.allowed_user_emails:
        store.delete(user_id)
        return JSONResponse(
            {"error": "UNAUTHORIZED_USER", "message": f"User {email} is not authorized to access this assistant."},
            status_code=403,
        )
    request.session["user_id"] = user_id
    request.session.pop("oauth_state", None)

    # Append auth_token so cross-domain 3rd party cookie blocking (Chrome/Safari/Render) never breaks auth
    sep = "&" if "?" in base_redirect else "?"
    redirect_url = f"{base_redirect}{sep}auth_token={user_id}"

    # Use 200 OK HTML response so browsers commit the Set-Cookie header before cross-origin navigation
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Authenticating...</title>
<script>
  window.location.href = "{redirect_url}";
</script>
</head>
<body style="background:#090d16;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;">
  <div style="text-align:center;padding:32px;background:#131b2e;border-radius:16px;box-shadow:0 10px 25px rgba(0,0,0,0.5);">
    <div style="font-size:24px;margin-bottom:12px;">✅</div>
    <h2 style="margin:0 0 8px 0;font-size:20px;">Authentication Successful</h2>
    <p style="margin:0;color:#94a3b8;font-size:14px;">Redirecting to your executive assistant workspace...</p>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/status")
def status(request: Request):
    user_id = deps.get_user_id_from_request(request)
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
    user_id = deps.get_user_id_from_request(request)
    request.session.pop("user_id", None)
    if user_id:
        store.delete(user_id)
    return {"ok": True}
