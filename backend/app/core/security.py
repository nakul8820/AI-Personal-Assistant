"""Token encryption at rest via Fernet."""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    secret = get_settings().session_secret.encode("utf-8")
    fallback_key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest()).decode("utf-8")
    
    if not key:
        key = fallback_key
    try:
        return Fernet(key.encode("utf-8"))
    except Exception:
        return Fernet(fallback_key.encode("utf-8"))


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext string into a UTF-8 string token."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str | bytes) -> str:
    """Decrypt a token string or bytes back to plaintext."""
    if isinstance(token, str):
        token_bytes = token.encode("utf-8")
    elif isinstance(token, memoryview):
        token_bytes = bytes(token)
    else:
        token_bytes = token
    return _fernet().decrypt(token_bytes).decode("utf-8")
