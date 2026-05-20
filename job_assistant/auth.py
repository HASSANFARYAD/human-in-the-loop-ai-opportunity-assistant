from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from job_assistant.config import settings
from job_assistant.db import create_session_token, create_user, get_user, get_user_by_email, get_user_by_session_token, revoke_session_token

PASSWORD_HASH_ITERATIONS = 600_000

try:
    from fastapi import Depends, HTTPException, status
    from fastapi.security import OAuth2PasswordBearer

    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
except ModuleNotFoundError:
    Depends = None
    HTTPException = None
    status = None
    oauth2_scheme = None


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_HASH_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash or password_hash.startswith("legacy:"):
        return False
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        return secrets.compare_digest(digest.hex(), expected)
    except Exception:
        return False


def authenticate_user(email: str, password: str) -> dict[str, Any]:
    user = get_user_by_email(email)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return {}
    if not user.get("is_active"):
        return {}
    return user


def register_user(email: str, password: str, full_name: str = "") -> dict[str, Any]:
    existing = get_user_by_email(email)
    if existing:
        raise ValueError("Email already registered")
    user_id = create_user(email=email, password_hash=hash_password(password), full_name=full_name)
    return get_user(user_id)


def create_access_token(user: dict[str, Any]) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def user_from_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError):
        return {}
    return get_user(user_id)


def _current_user_from_token(token: str) -> dict[str, Any]:
    if HTTPException is None or status is None:
        raise RuntimeError("FastAPI is required for API bearer-token authentication.")
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub", "0"))
    except (JWTError, ValueError):
        raise credentials_error
    user = get_user(user_id)
    if not user:
        raise credentials_error
    return user


if Depends is not None and oauth2_scheme is not None:

    def current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
        return _current_user_from_token(token)

else:

    def current_user(token: str = "") -> dict[str, Any]:
        return _current_user_from_token(token)


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "created_at": user.get("created_at", ""),
    }


def create_refresh_token(user: dict[str, Any], days: int = 30) -> str:
    return create_session_token(int(user["id"]), days=days)


def user_from_refresh_token(token: str) -> dict[str, Any]:
    return get_user_by_session_token(token)


def revoke_refresh_token(token: str) -> None:
    revoke_session_token(token)
