"""Google OAuth 2.0 (offline) + credential retrieval with auto-refresh.

The tool layer calls `credentials_for(user_id)` to get live google.oauth2
Credentials; refresh failures surface as GoogleAuthError (-> AUTH_EXPIRED),
never a raw exception.
"""

import base64
import hashlib

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.auth import store
from app.core.config import get_settings
from app.core.errors import GoogleAuthError


def _pkce_verifier(state: str) -> str:
    """Generate a deterministic RFC-7636 compliant PKCE code_verifier from state & session secret."""
    secret = get_settings().session_secret
    raw = hashlib.sha256(f"pkce:{state}:{secret}".encode()).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=").replace("+", "-").replace("/", "_")


def _flow(state: str | None = None) -> Flow:
    s = get_settings()
    client_config = {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [s.oauth_redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=s.google_scopes,
        redirect_uri=s.oauth_redirect_uri,
        state=state,
    )


def authorization_url(state: str) -> str:
    flow = _flow(state)
    flow.code_verifier = _pkce_verifier(state)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # force refresh_token on every consent
    )
    return url


def _creds_to_dict(c: Credentials) -> dict:
    return {
        "token": c.token,
        "refresh_token": c.refresh_token,
        "token_uri": c.token_uri,
        "client_id": c.client_id,
        "client_secret": c.client_secret,
        "scopes": c.scopes,
    }


def exchange_code(code: str, state: str) -> tuple[str, str]:
    """Finish the flow; persist tokens. Returns (user_id, email)."""
    flow = _flow(state)
    flow.code_verifier = _pkce_verifier(state)
    flow.fetch_token(code=code)
    creds = flow.credentials

    email, name = _userinfo_email_and_name(creds)
    user_id = email  # email is a stable per-user key for this app
    
    creds_dict = _creds_to_dict(creds)
    if name:
        creds_dict["user_name"] = name
        
    store.save(user_id, email, creds_dict)
    return user_id, email


def _userinfo_email_and_name(creds: Credentials) -> tuple[str, str | None]:
    from googleapiclient.discovery import build

    svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
    info = svc.userinfo().get().execute()
    return info.get("email"), info.get("name")


def credentials_for(user_id: str) -> Credentials:
    data = store.load(user_id)
    if not data:
        raise GoogleAuthError("No stored credentials; please connect Google.")
    creds = Credentials(**data)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise GoogleAuthError("Google connection expired; reauthenticate.") from e
        store.save(user_id, store.email_for(user_id) or user_id, _creds_to_dict(creds))
    if not creds.valid:
        raise GoogleAuthError("Google credentials invalid; reauthenticate.")
    return creds
