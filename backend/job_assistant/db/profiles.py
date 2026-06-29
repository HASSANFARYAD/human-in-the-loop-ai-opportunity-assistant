from __future__ import annotations

from typing import Any, Dict

import pymongo

from job_assistant.db.core import _next_id, _strip_id, get_collection, utc_now

__all__ = [
    "PROFILE_FIELDS",
    "_default_profile_id", "upsert_profile", "create_profile",
    "update_profile_fields", "set_default_profile", "delete_profile",
    "_profile_with_id_alias", "list_profiles", "get_profile",
]


PROFILE_FIELDS = [
    "cv_text", "target_roles", "industries", "locations", "remote_preference",
    "salary_expectations", "work_authorization", "years_experience", "skills",
    "deal_breakers", "full_name", "email", "preferred_role", "country",
    "job_preferences", "platforms", "resume_name", "integration_status",
]


def _default_profile_id(user_id: int) -> int | None:
    doc = get_collection("profiles").find_one({"user_id": user_id}, sort=[("is_default", pymongo.DESCENDING), ("_id", pymongo.ASCENDING)])
    return int(doc["profile_id"]) if doc else None


def upsert_profile(profile: Dict[str, Any], user_id: int = 1, profile_id: int | None = None) -> int:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    profiles = get_collection("profiles")
    target_id = profile_id or _default_profile_id(user_id)
    if target_id is not None:
        profiles.update_one({"profile_id": target_id, "user_id": user_id}, {"$set": {**values, "updated_at": now}})
        return int(target_id)
    name = (profile.get("name") or "Default").strip() or "Default"
    pid = _next_id("profile_id")
    profiles.insert_one({"profile_id": pid, "user_id": user_id, "name": name, "is_default": 1, **values, "created_at": now, "updated_at": now})
    return pid


def create_profile(user_id: int, profile: Dict[str, Any], name: str = "", make_default: bool = False) -> int:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    clean_name = (name or profile.get("name") or "").strip() or "New profile"
    profiles = get_collection("profiles")
    has_any = profiles.find_one({"user_id": user_id})
    is_default = 1 if (make_default or not has_any) else 0
    base, suffix = clean_name, 2
    while profiles.find_one({"user_id": user_id, "name": clean_name}):
        clean_name = f"{base} ({suffix})"
        suffix += 1
    if is_default:
        profiles.update_many({"user_id": user_id}, {"$set": {"is_default": 0}})
    pid = _next_id("profile_id")
    profiles.insert_one({"profile_id": pid, "user_id": user_id, "name": clean_name, "is_default": is_default, **values, "created_at": now, "updated_at": now})
    return pid


def update_profile_fields(user_id: int, profile_id: int, profile: Dict[str, Any]) -> bool:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    profiles = get_collection("profiles")
    existing = profiles.find_one({"profile_id": profile_id, "user_id": user_id})
    if not existing:
        return False
    updates = {**values, "updated_at": now}
    if profile.get("name"):
        new_name = profile["name"].strip()
        if new_name and not profiles.find_one({"user_id": user_id, "name": new_name, "profile_id": {"$ne": profile_id}}):
            updates["name"] = new_name
    profiles.update_one({"profile_id": profile_id, "user_id": user_id}, {"$set": updates})
    return True


def set_default_profile(user_id: int, profile_id: int) -> bool:
    profiles = get_collection("profiles")
    if not profiles.find_one({"profile_id": profile_id, "user_id": user_id}):
        return False
    profiles.update_many({"user_id": user_id}, {"$set": {"is_default": 0}})
    profiles.update_one({"profile_id": profile_id, "user_id": user_id}, {"$set": {"is_default": 1}})
    return True


def delete_profile(user_id: int, profile_id: int) -> bool:
    profiles = get_collection("profiles")
    count = profiles.count_documents({"user_id": user_id})
    if count <= 1:
        raise ValueError("Cannot delete your only profile.")
    doc = profiles.find_one({"profile_id": profile_id, "user_id": user_id})
    if not doc:
        return False
    profiles.delete_one({"profile_id": profile_id, "user_id": user_id})
    if doc.get("is_default"):
        next_profile = profiles.find_one({"user_id": user_id}, sort=[("_id", pymongo.DESCENDING)])
        if next_profile:
            profiles.update_one({"_id": next_profile["_id"]}, {"$set": {"is_default": 1}})
    return True


def _profile_with_id_alias(doc: dict) -> dict:
    item = _strip_id(doc)
    if item and "profile_id" in item:
        item["id"] = item["profile_id"]
    return item


def list_profiles(user_id: int) -> list[dict[str, Any]]:
    docs = get_collection("profiles").find({"user_id": user_id}).sort([("is_default", pymongo.DESCENDING), ("name", pymongo.ASCENDING)])
    return [_profile_with_id_alias(d) for d in docs]


def get_profile(user_id: int = 1, profile_id: int | None = None) -> Dict[str, Any]:
    profiles = get_collection("profiles")
    if profile_id is not None:
        doc = profiles.find_one({"profile_id": profile_id, "user_id": user_id})
    else:
        doc = profiles.find_one({"user_id": user_id}, sort=[("is_default", pymongo.DESCENDING), ("_id", pymongo.ASCENDING)])
    return _profile_with_id_alias(doc) if doc else {}
