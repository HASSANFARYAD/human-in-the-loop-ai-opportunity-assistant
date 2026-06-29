from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from job_assistant.db.core import (
    _next_id, _strip_id, get_collection, utc_now,
)

__all__ = [
    "cache_company_profile",
    "get_cached_company_profile",
    "list_cached_companies",
    "delete_cached_company_profile",
    "COMPANY_CACHE_TTL_DAYS",
]

COMPANY_CACHE_TTL_DAYS = 7


def cache_company_profile(
    company_name: str,
    profile: Dict[str, Any],
    source: str = "ai_research",
    *,
    user_id: Optional[int] = None,
) -> None:
    try:
        normalized = company_name.strip().lower()
        existing = get_collection("company_profiles").find_one({"normalized_name": normalized})
        record = {
            "normalized_name": normalized,
            "display_name": company_name.strip(),
            "profile": profile,
            "source": source,
            "cached_by_user_id": user_id,
            "updated_at": utc_now(),
            "expires_at": utc_now() + timedelta(days=COMPANY_CACHE_TTL_DAYS),
        }
        if existing:
            get_collection("company_profiles").update_one(
                {"_id": existing["_id"]},
                {"$set": record},
            )
        else:
            record["created_at"] = utc_now()
            record["company_profile_id"] = _next_id("company_profile_id")
            get_collection("company_profiles").insert_one(record)
    except Exception:
        pass


def get_cached_company_profile(company_name: str) -> Optional[Dict[str, Any]]:
    normalized = company_name.strip().lower()
    try:
        row = get_collection("company_profiles").find_one({
            "normalized_name": normalized,
            "expires_at": {"$gt": utc_now()},
        })
        if not row:
            return None
        return _strip_id(row)
    except Exception:
        return None


def list_cached_companies(limit: int = 50) -> list[Dict[str, Any]]:
    rows = (
        get_collection("company_profiles")
        .find({"expires_at": {"$gt": utc_now()}})
        .sort("updated_at", -1)
        .limit(max(1, limit))
    )
    return [_strip_id(row) for row in rows]


def delete_cached_company_profile(company_name: str) -> bool:
    normalized = company_name.strip().lower()
    result = get_collection("company_profiles").delete_one({"normalized_name": normalized})
    return result.deleted_count > 0
