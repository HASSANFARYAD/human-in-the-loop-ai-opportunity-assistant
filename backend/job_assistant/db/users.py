from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from job_assistant.db.core import _next_id, _token_hash, _strip_id, get_collection, utc_now

__all__ = [
    "create_user", "_user_with_id_alias", "get_user_by_email", "get_user",
    "create_session_token", "get_user_by_session_token", "revoke_session_token",
    "create_password_reset_token", "get_password_reset_token",
    "consume_password_reset_token",
    "update_user_password", "revoke_user_sessions",
]


def create_user(email: str, password_hash: str, full_name: str = "") -> int:
    now = utc_now()
    user_id = _next_id("user_id")
    get_collection("users").insert_one({
        "user_id": user_id,
        "email": email.strip().lower(),
        "lower_email": email.strip().lower(),
        "password_hash": password_hash,
        "full_name": full_name.strip(),
        "is_active": 1,
        "created_at": now,
        "updated_at": now,
    })
    return user_id


def _user_with_id_alias(doc: dict) -> dict:
    item = _strip_id(doc)
    if item and "user_id" in item:
        item["id"] = item["user_id"]
    return item


def get_user_by_email(email: str) -> dict[str, Any]:
    doc = get_collection("users").find_one({"lower_email": email.strip().lower()})
    return _user_with_id_alias(doc) if doc else {}


def get_user(user_id: int) -> dict[str, Any]:
    doc = get_collection("users").find_one({"user_id": user_id, "is_active": 1})
    return _user_with_id_alias(doc) if doc else {}


def create_session_token(user_id: int, days: int = 30) -> str:
    token = secrets.token_urlsafe(48)
    now = utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
    get_collection("user_sessions").insert_one({
        "user_id": user_id, "token_hash": _token_hash(token),
        "created_at": now, "expires_at": expires_at,
    })
    return token


def get_user_by_session_token(token: str) -> dict[str, Any]:
    if not token:
        return {}
    doc = get_collection("user_sessions").find_one({
        "token_hash": _token_hash(token), "revoked_at": None,
        "expires_at": {"$gt": utc_now()},
    })
    if not doc:
        return {}
    user = get_collection("users").find_one({"user_id": doc["user_id"], "is_active": 1})
    return _user_with_id_alias(user) if user else {}


def revoke_session_token(token: str) -> None:
    if not token:
        return
    get_collection("user_sessions").update_one(
        {"token_hash": _token_hash(token)},
        {"$set": {"revoked_at": utc_now()}},
    )


def create_password_reset_token(user_id: int, token: str, expires_at: str, ip_address: str = "", user_agent: str = "") -> int:
    now = utc_now()
    tid = _next_id("password_reset_token_id")
    get_collection("password_reset_tokens").insert_one({
        "password_reset_token_id": tid, "user_id": user_id,
        "token_hash": _token_hash(token), "created_at": now,
        "expires_at": expires_at, "ip_address": ip_address,
        "user_agent": user_agent,
    })
    return tid


def get_password_reset_token(token: str) -> dict[str, Any]:
    if not token:
        return {}
    now = utc_now()
    token_hash = _token_hash(token)
    doc = get_collection("password_reset_tokens").find_one({
        "token_hash": token_hash, "consumed_at": None,
        "expires_at": {"$gt": now},
    })
    if not doc:
        return {}
    user = get_collection("users").find_one({"user_id": doc["user_id"], "is_active": 1})
    item = _strip_id(doc)
    if user:
        item["email"] = user.get("email")
        item["user_email"] = user.get("email")
    return item


def consume_password_reset_token(token_id: int) -> bool:
    result = get_collection("password_reset_tokens").update_one(
        {"password_reset_token_id": token_id, "consumed_at": None},
        {"$set": {"consumed_at": utc_now()}},
    )
    return result.modified_count == 1


def update_user_password(user_id: int, password_hash: str) -> None:
    get_collection("users").update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": password_hash, "updated_at": utc_now()}},
    )


def revoke_user_sessions(user_id: int) -> None:
    get_collection("user_sessions").update_many(
        {"user_id": user_id, "revoked_at": None},
        {"$set": {"revoked_at": utc_now()}},
    )
