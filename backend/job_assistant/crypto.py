from __future__ import annotations

"""Application-level encryption helpers for user secrets.

Secrets are encrypted before they are stored in the database. The master key must
be supplied through APP_ENCRYPTION_KEY in production. Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import base64
import hashlib
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:v1:"
_DEV_KEY_SEED = "dev-only-job-assistant-encryption-key-change-me"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw_key = os.getenv("APP_ENCRYPTION_KEY", "").strip()
    if raw_key:
        key = raw_key.encode("utf-8")
    else:
        # Development fallback keeps local demos usable. Production must provide
        # APP_ENCRYPTION_KEY so encrypted data can survive deployments securely.
        digest = hashlib.sha256(_DEV_KEY_SEED.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(_PREFIX))


def encrypt_text(value: str | None) -> str:
    if not value:
        return ""
    if is_encrypted(value):
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def decrypt_text(value: str | None) -> str:
    if not value:
        return ""
    if not is_encrypted(value):
        # Gracefully handle older plaintext rows so users can migrate by saving.
        return value
    token = value[len(_PREFIX) :].encode("utf-8")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken:
        return ""


def mask_secret(value: str | None, visible: int = 4) -> str:
    if not value:
        return "Not configured"
    if len(value) <= visible * 2:
        return "Configured"
    return f"{value[:visible]}...{value[-visible:]}"
