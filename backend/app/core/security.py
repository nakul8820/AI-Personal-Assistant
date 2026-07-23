"""Token encryption at rest via Fernet."""

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        # ponytail: dev fallback generates an ephemeral key => tokens don't
        # survive restart. Set TOKEN_ENCRYPTION_KEY in prod for persistence.
        key = Fernet.generate_key().decode()
    return Fernet(key.encode())


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(token: bytes) -> str:
    return _fernet().decrypt(token).decode()
