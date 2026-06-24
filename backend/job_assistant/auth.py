from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from job_assistant.config import settings
from job_assistant.db import (
    consume_password_reset_token,
    create_password_reset_token,
    create_session_token,
    create_user,
    get_user,
    get_user_by_email,
    get_user_by_session_token,
    get_password_reset_token,
    revoke_session_token,
    revoke_user_sessions,
    update_user_password,
)
from job_assistant.email_delivery import send_password_reset_email

PASSWORD_HASH_ITERATIONS = 600_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "changeme",
    "changeme123",
    "12345678",
    "qwerty123",
}

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


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized or len(normalized) > 254 or not EMAIL_RE.match(normalized):
        raise ValueError("A valid email address is required")
    return normalized


def validate_password_policy(password: str, email: str = "") -> None:
    if len(password or "") < 12:
        raise ValueError("Password must be at least 12 characters")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        raise ValueError("Password is too common")
    local_part = (email or "").split("@", 1)[0].lower()
    if local_part and len(local_part) >= 4 and local_part in lowered:
        raise ValueError("Password must not contain your email username")
    checks = [
        any(ch.islower() for ch in password),
        any(ch.isupper() for ch in password),
        any(ch.isdigit() for ch in password),
        any(not ch.isalnum() for ch in password),
    ]
    if sum(checks) < 3:
        raise ValueError("Password must include at least three of: lowercase, uppercase, number, symbol")


def authenticate_user(email: str, password: str) -> dict[str, Any]:
    try:
        email = normalize_email(email)
    except ValueError:
        return {}
    user = get_user_by_email(email)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return {}
    if not user.get("is_active"):
        return {}
    return user


def register_user(email: str, password: str, full_name: str = "") -> dict[str, Any]:
    email = normalize_email(email)
    validate_password_policy(password, email)
    existing = get_user_by_email(email)
    if existing:
        raise ValueError("Email already registered")
    user_id = create_user(email=email, password_hash=hash_password(password), full_name=full_name)
    return get_user(user_id)


def request_password_reset(email: str, reset_url_base: str, ip_address: str = "", user_agent: str = "") -> None:
    try:
        email = normalize_email(email)
    except ValueError:
        return
    user = get_user_by_email(email)
    if not user or not user.get("is_active"):
        return
    token = secrets.token_urlsafe(48)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_expire_minutes)).isoformat(timespec="seconds")
    create_password_reset_token(int(user["user_id"]), token, expires_at, ip_address=ip_address, user_agent=user_agent)
    separator = "&" if "?" in reset_url_base else "?"
    send_password_reset_email(email, f"{reset_url_base}{separator}token={token}")


def reset_password(token: str, new_password: str) -> bool:
    reset_token = get_password_reset_token(token)
    if not reset_token:
        return False
    user = get_user(int(reset_token["user_id"]))
    if not user:
        return False
    validate_password_policy(new_password, user.get("email", ""))
    if not consume_password_reset_token(int(reset_token["password_reset_token_id"])):
        return False
    update_user_password(int(user["user_id"]), hash_password(new_password))
    revoke_user_sessions(int(user["user_id"]))
    return True


def create_access_token(user: dict[str, Any]) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user["user_id"]),
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
        "id": user["user_id"],
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "created_at": user.get("created_at", ""),
    }


def create_refresh_token(user: dict[str, Any], days: int = 30) -> str:
    return create_session_token(int(user["user_id"]), days=days)


def user_from_refresh_token(token: str) -> dict[str, Any]:
    return get_user_by_session_token(token)


def revoke_refresh_token(token: str) -> None:
    revoke_session_token(token)
