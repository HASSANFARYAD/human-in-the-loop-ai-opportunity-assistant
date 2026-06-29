from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict

import pymongo
from pymongo import errors as pymongo_errors

from job_assistant.db.core import (
    _next_id, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
)

__all__ = [
    "increment_usage_counter", "usage_summary", "log_ai_generation",
    "record_score_feedback", "recent_score_feedback",
    "count_ai_generations_today", "list_ai_generations", "ai_usage_detailed",
    "get_rate_limit_status",
    "upsert_prompt_version", "list_prompt_versions", "get_active_prompt", "delete_prompt_version",
]


def increment_usage_counter(
    *, resource_type: str, window_start: str, window_end: str,
    user_id: int | None = None, ip_address: str = "",
) -> int:
    now = utc_now()
    counter_user_id = int(user_id) if user_id is not None else -1
    col = get_collection("usage_counters")
    col.delete_many({"window_end": {"$lt": now}})
    try:
        col.update_one(
            {"user_id": counter_user_id, "ip_address": ip_address or "", "resource_type": resource_type, "window_start": window_start},
            {"$inc": {"count": 1}, "$set": {"window_end": window_end, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except pymongo_errors.DuplicateKeyError:
        col.update_one(
            {"user_id": counter_user_id, "ip_address": ip_address or "", "resource_type": resource_type, "window_start": window_start},
            {"$inc": {"count": 1}, "$set": {"window_end": window_end, "updated_at": now}},
        )
    doc = col.find_one({"user_id": counter_user_id, "ip_address": ip_address or "", "resource_type": resource_type, "window_start": window_start})
    return int(doc["count"]) if doc else 1


def usage_summary(user_id: int | None = None) -> list[dict[str, Any]]:
    now = utc_now()
    q: dict[str, Any] = {"window_end": {"$gte": now}}
    if user_id is not None:
        q["user_id"] = user_id
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$resource_type",
            "count": {"$sum": "$count"},
            "window_start": {"$min": "$window_start"},
            "window_end": {"$max": "$window_end"},
        }},
        {"$sort": {"_id": pymongo.ASCENDING}},
    ]
    results = []
    for doc in get_collection("usage_counters").aggregate(pipeline):
        results.append({
            "resource_type": doc["_id"],
            "count": doc["count"],
            "window_start": doc["window_start"],
            "window_end": doc["window_end"],
        })
    return results


def log_ai_generation(
    user_id: int | None, *, provider: str = "", model: str = "",
    task_type: str = "general", prompt_version: str = "", prompt_hash: str = "",
    input_tokens: int = 0, output_tokens: int = 0, estimated_cost: float = 0.0,
    latency_ms: int | None = None, status: str = "unknown",
    error_message: str = "", workspace_id: int | None = None,
) -> int:
    scoped_workspace_id = None
    organization_id = None
    if user_id:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    gid = _next_id("ai_generation_id")
    get_collection("ai_generations").insert_one({
        "ai_generation_id": gid, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "provider": provider, "model": model, "task_type": task_type,
        "prompt_version": prompt_version, "prompt_hash": prompt_hash,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "estimated_cost": float(estimated_cost or 0),
        "latency_ms": latency_ms, "status": status,
        "error_message": error_message, "created_at": utc_now(),
    })
    return gid


def record_score_feedback(user_id: int, job_id: int, signal: str, workspace_id: int | None = None) -> int:
    signal = (signal or "").strip().lower()
    if signal not in ("relevant", "irrelevant"):
        raise ValueError("signal must be 'relevant' or 'irrelevant'")
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    sfid = _next_id("score_feedback_id")
    get_collection("score_feedback").insert_one({
        "score_feedback_id": sfid, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "job_id": job_id,
        "signal": signal, "created_at": utc_now(),
    })
    return sfid


def recent_score_feedback(user_id: int, limit: int = 10, workspace_id: int | None = None) -> list[dict[str, Any]]:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort": {"_id": pymongo.DESCENDING}},
        {"$limit": max(1, min(int(limit), 50))},
        {"$lookup": {"from": "jobs", "localField": "job_id", "foreignField": "job_id", "as": "job"}},
        {"$unwind": {"path": "$job", "preserveNullAndEmptyArrays": True}},
        {"$project": {"signal": 1, "created_at": 1, "title": "$job.title", "company": "$job.company"}},
    ]
    return list(get_collection("score_feedback").aggregate(pipeline))


def count_ai_generations_today(user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    count = get_collection("ai_generations").count_documents({
        "user_id": user_id,
        "created_at": {"$regex": f"^{today}"},
        "provider": {"$nin": [None, "", "none"]},
    })
    return count


def list_ai_generations(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("ai_generations").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def ai_usage_detailed(user_id: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    thirty_days_ago = (now - timedelta(days=30)).isoformat(timespec="seconds")

    def _agg(start: str) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"user_id": user_id, "created_at": {"$gte": start}}},
            {"$group": {
                "_id": "$task_type",
                "calls": {"$sum": 1},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "estimated_cost": {"$sum": "$estimated_cost"},
                "latency_ms": {"$avg": "$latency_ms"},
            }},
            {"$sort": {"calls": pymongo.DESCENDING}},
        ]
        results = []
        for doc in get_collection("ai_generations").aggregate(pipeline):
            results.append({
                "task_type": doc["_id"] or "unknown",
                "calls": doc["calls"],
                "input_tokens": doc["input_tokens"],
                "output_tokens": doc["output_tokens"],
                "estimated_cost": round(doc["estimated_cost"], 6),
                "avg_latency_ms": int(doc["latency_ms"] or 0),
            })
        return results

    def _daily() -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"user_id": user_id, "created_at": {"$gte": thirty_days_ago}}},
            {"$project": {"day": {"$substr": ["$created_at", 0, 10]}, "input_tokens": 1, "output_tokens": 1, "estimated_cost": 1, "status": 1}},
            {"$group": {
                "_id": "$day",
                "calls": {"$sum": 1},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "estimated_cost": {"$sum": "$estimated_cost"},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            }},
            {"$sort": {"_id": pymongo.DESCENDING}},
        ]
        results = []
        for doc in get_collection("ai_generations").aggregate(pipeline):
            results.append({
                "date": doc["_id"],
                "calls": doc["calls"],
                "input_tokens": doc["input_tokens"],
                "output_tokens": doc["output_tokens"],
                "estimated_cost": round(doc["estimated_cost"], 6),
                "failed": doc["failed"],
            })
        return results

    today_agg = _agg(today_start)
    total_today = {"calls": sum(r["calls"] for r in today_agg), "input_tokens": sum(r["input_tokens"] for r in today_agg), "output_tokens": sum(r["output_tokens"] for r in today_agg), "estimated_cost": round(sum(r["estimated_cost"] for r in today_agg), 6)}
    week_agg = _agg(week_start)
    total_week = {"calls": sum(r["calls"] for r in week_agg), "input_tokens": sum(r["input_tokens"] for r in week_agg), "output_tokens": sum(r["output_tokens"] for r in week_agg), "estimated_cost": round(sum(r["estimated_cost"] for r in week_agg), 6)}
    month_agg = _agg(month_start)
    total_month = {"calls": sum(r["calls"] for r in month_agg), "input_tokens": sum(r["input_tokens"] for r in month_agg), "output_tokens": sum(r["output_tokens"] for r in month_agg), "estimated_cost": round(sum(r["estimated_cost"] for r in month_agg), 6)}

    return {
        "today": {"total": total_today, "by_task_type": today_agg},
        "this_week": {"total": total_week, "by_task_type": week_agg},
        "this_month": {"total": total_month, "by_task_type": month_agg},
        "daily_history": _daily(),
    }


def get_rate_limit_status() -> list[dict[str, Any]]:
    now = utc_now()
    from job_assistant.config import settings
    limits = [
        ("ai_generation", settings.rate_limit_ai_per_hour, 60),
        ("sse_chat", settings.rate_limit_sse_per_minute, 1),
        ("feedback", settings.rate_limit_feedback_per_hour, 60),
        ("publishing", settings.rate_limit_publish_per_hour, 60),
        ("api_request", settings.rate_limit_per_minute, 1),
    ]
    results = []
    for resource_type, limit, window_minutes in limits:
        if limit <= 0:
            continue
        if window_minutes >= 60:
            hours = window_minutes // 60
            start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            window_start = start.isoformat(timespec="seconds")
            window_end = (start + timedelta(hours=hours)).isoformat(timespec="seconds")
        else:
            start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            window_start = start.isoformat(timespec="seconds")
            window_end = (start + timedelta(minutes=window_minutes)).isoformat(timespec="seconds")
        docs = get_collection("usage_counters").find({"resource_type": resource_type, "window_start": window_start})
        count = sum(int(d.get("count", 0)) for d in docs)
        results.append({
            "resource_type": resource_type,
            "limit": limit,
            "used": count,
            "remaining": max(0, limit - count),
            "window_start": window_start,
            "window_end": window_end,
        })
    return results


def upsert_prompt_version(name: str, version: str, template: str, description: str = "", is_active: bool = True) -> None:
    now = utc_now()
    get_collection("prompt_versions").update_one(
        {"name": name, "version": version},
        {"$set": {"description": description, "template": template, "is_active": 1 if is_active else 0, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


def list_prompt_versions(limit: int = 100) -> list[dict[str, Any]]:
    docs = get_collection("prompt_versions").find().sort([("name", pymongo.ASCENDING), ("version", pymongo.ASCENDING)]).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def get_active_prompt(name: str) -> str:
    doc = get_collection("prompt_versions").find_one(
        {"name": name, "is_active": 1},
        sort=[("version", pymongo.DESCENDING)],
    )
    if doc:
        return doc.get("template", "")
    return ""


def delete_prompt_version(name: str, version: str) -> bool:
    result = get_collection("prompt_versions").delete_one({"name": name, "version": version})
    return result.deleted_count > 0
