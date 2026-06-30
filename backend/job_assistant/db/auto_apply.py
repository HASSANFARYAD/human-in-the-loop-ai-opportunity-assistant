from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

import pymongo

from job_assistant.db.core import (
    _next_id, _safe_json_loads, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
)

__all__ = [
    "create_auto_apply_log", "update_auto_apply_log",
    "list_auto_apply_logs", "get_auto_apply_stats",
    "get_daily_apply_count", "get_auto_apply_log",
    "get_pending_approval_logs",
]

APPLY_CHANNELS = ("linkedin_easy_apply", "email", "ats_form")
APPLY_STATUSES = ("pending", "submitted", "failed", "skipped", "budget_exceeded", "needs_approval")


def create_auto_apply_log(
    user_id: int,
    job_id: int,
    channel: str,
    loop_id: int | None = None,
    run_id: int | None = None,
    score: int | None = None,
    workspace_id: int | None = None,
) -> int:
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    if channel not in APPLY_CHANNELS:
        channel = "email"
    log_id = _next_id("auto_apply_log_id")
    get_collection("auto_apply_logs").insert_one({
        "auto_apply_log_id": log_id,
        "user_id": user_id,
        "workspace_id": scoped_workspace_id,
        "organization_id": organization_id,
        "loop_id": loop_id,
        "run_id": run_id,
        "job_id": job_id,
        "channel": channel,
        "status": "pending",
        "score": score,
        "error_message": None,
        "details_json": "{}",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    })
    return log_id


def update_auto_apply_log(
    log_id: int,
    user_id: int,
    *,
    status: str,
    error_message: str = None,
    details: dict[str, Any] = None,
) -> None:
    if status not in APPLY_STATUSES:
        status = "failed"
    updates: dict[str, Any] = {
        "status": status,
        "updated_at": utc_now(),
    }
    if error_message is not None:
        updates["error_message"] = str(error_message)[:2000]
    if details is not None:
        updates["details_json"] = json.dumps(details)
    get_collection("auto_apply_logs").update_one(
        {"auto_apply_log_id": log_id, "user_id": user_id},
        {"$set": updates},
    )


def get_auto_apply_log(log_id: int, user_id: int) -> dict[str, Any] | None:
    doc = get_collection("auto_apply_logs").find_one({"auto_apply_log_id": log_id, "user_id": user_id})
    if not doc:
        return None
    item = _strip_id(doc)
    item["details"] = _safe_json_loads(item.pop("details_json", "{}"), {})
    return item


def list_auto_apply_logs(
    user_id: int,
    limit: int = 100,
    status: str = None,
    loop_id: int = None,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    q: dict[str, Any] = {"user_id": user_id, "workspace_id": scoped_workspace_id}
    if status:
        q["status"] = status
    if loop_id is not None:
        q["loop_id"] = loop_id
    docs = get_collection("auto_apply_logs").find(q).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    out = []
    for d in docs:
        item = _strip_id(d)
        item["details"] = _safe_json_loads(item.pop("details_json", "{}"), {})
        out.append(item)
    return out


def get_auto_apply_stats(user_id: int, workspace_id: int | None = None, days: int = 30) -> dict[str, Any]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() if days else "1970-01-01T00:00:00"
    match = {"user_id": user_id, "workspace_id": scoped_workspace_id, "created_at": {"$gte": cutoff}}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
        }},
    ]
    results = get_collection("auto_apply_logs").aggregate(pipeline)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["_id"]] = r["count"]
    total = sum(counts.values())
    return {
        "total": total,
        "submitted": counts.get("submitted", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "pending": counts.get("pending", 0),
        "needs_approval": counts.get("needs_approval", 0),
        "budget_exceeded": counts.get("budget_exceeded", 0),
        "period_days": days,
    }


def get_daily_apply_count(user_id: int, workspace_id: int | None = None) -> int:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    today_start = utc_now()[:10] + "T00:00:00"
    return get_collection("auto_apply_logs").count_documents({
        "user_id": user_id,
        "workspace_id": scoped_workspace_id,
        "status": "submitted",
        "created_at": {"$gte": today_start},
    })


def get_pending_approval_logs(user_id: int, workspace_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("auto_apply_logs").find({
        "user_id": user_id,
        "workspace_id": scoped_workspace_id,
        "status": "needs_approval",
    }).sort("created_at", pymongo.ASCENDING).limit(max(1, min(int(limit), 500)))
    out = []
    for d in docs:
        item = _strip_id(d)
        item["details"] = _safe_json_loads(item.pop("details_json", "{}"), {})
        out.append(item)
    return out
