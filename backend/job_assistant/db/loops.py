from __future__ import annotations

import json
from typing import Any

import pymongo

from job_assistant.db.core import (
    _next_id, _safe_json_loads, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
)

__all__ = [
    "create_loop", "get_loop", "list_loops", "update_loop", "delete_loop",
    "create_loop_run", "update_loop_run", "list_loop_runs",
    "get_loop_daily_usage", "get_active_loops",
]


def create_loop(user_id: int, payload: dict[str, Any], workspace_id: int | None = None) -> int:
    now = utc_now()
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id or payload.get("workspace_id"))
    lid = _next_id("loop_id")
    doc = {
        "loop_id": lid,
        "user_id": user_id,
        "workspace_id": scoped_workspace_id,
        "organization_id": organization_id,
        "name": str(payload.get("name") or "Untitled Loop"),
        "search_query": str(payload.get("search_query") or ""),
        "sources": list(payload.get("sources") or ["LinkedIn", "RemoteJobs.org", "Arbeitnow"]),
        "platforms": list(payload.get("platforms") or ["linkedin", "email"]),
        "is_active": 1 if payload.get("is_active", True) else 0,
        "auto_apply_enabled": 1 if payload.get("auto_apply_enabled", False) else 0,
        "daily_budget": max(0, int(payload.get("daily_budget", 10))),
        "max_applications_per_run": max(1, int(payload.get("max_applications_per_run", 5))),
        "min_score_threshold": max(0, min(100, int(payload.get("min_score_threshold", 60)))),
        "channels": _normalize_channels(payload.get("channels")),
        "schedule_interval_hours": max(1, int(payload.get("schedule_interval_hours", 6))),
        "last_run_at": None,
        "created_at": now,
        "updated_at": now,
    }
    get_collection("loops").insert_one(doc)
    add_audit_log(user_id, "loop.create", "loop", str(lid), {"name": doc["name"]}, workspace_id=scoped_workspace_id, organization_id=organization_id)
    return lid


def get_loop(loop_id: int, user_id: int, workspace_id: int | None = None) -> dict[str, Any] | None:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    doc = get_collection("loops").find_one({"loop_id": loop_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    if not doc:
        return None
    return _format_loop(_strip_id(doc))


def list_loops(user_id: int, include_inactive: bool = False, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    q: dict[str, Any] = {"user_id": user_id, "workspace_id": scoped_workspace_id}
    if not include_inactive:
        q["is_active"] = 1
    docs = get_collection("loops").find(q).sort("created_at", pymongo.DESCENDING)
    return [_format_loop(_strip_id(d)) for d in docs]


def update_loop(loop_id: int, user_id: int, payload: dict[str, Any], workspace_id: int | None = None) -> dict[str, Any]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    current = get_collection("loops").find_one({"loop_id": loop_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    if not current:
        raise ValueError("Loop not found")

    updates: dict[str, Any] = {}
    for key in ("name", "search_query"):
        if key in payload:
            updates[key] = str(payload[key])
    if "sources" in payload:
        updates["sources"] = list(payload["sources"])
    if "platforms" in payload:
        updates["platforms"] = list(payload["platforms"])
    for key in ("is_active", "auto_apply_enabled"):
        if key in payload:
            updates[key] = 1 if payload[key] else 0
    if "daily_budget" in payload:
        updates["daily_budget"] = max(0, int(payload["daily_budget"]))
    if "max_applications_per_run" in payload:
        updates["max_applications_per_run"] = max(1, int(payload["max_applications_per_run"]))
    if "min_score_threshold" in payload:
        updates["min_score_threshold"] = max(0, min(100, int(payload["min_score_threshold"])))
    if "channels" in payload:
        updates["channels"] = _normalize_channels(payload["channels"])
    if "schedule_interval_hours" in payload:
        updates["schedule_interval_hours"] = max(1, int(payload["schedule_interval_hours"]))
    updates["updated_at"] = utc_now()

    if updates:
        get_collection("loops").update_one(
            {"loop_id": loop_id, "user_id": user_id, "workspace_id": scoped_workspace_id},
            {"$set": updates},
        )

    add_audit_log(user_id, "loop.update", "loop", str(loop_id), {"updated_fields": list(updates.keys())}, workspace_id=scoped_workspace_id, organization_id=current.get("organization_id"))
    return get_loop(loop_id, user_id, workspace_id=workspace_id)


def delete_loop(loop_id: int, user_id: int, workspace_id: int | None = None) -> None:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    current = get_collection("loops").find_one({"loop_id": loop_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    if current:
        get_collection("loops").delete_one({"loop_id": loop_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
        get_collection("loop_runs").delete_many({"loop_id": loop_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
        add_audit_log(user_id, "loop.delete", "loop", str(loop_id), {}, workspace_id=scoped_workspace_id, organization_id=current.get("organization_id"))


def create_loop_run(loop_id: int, user_id: int, workspace_id: int | None = None) -> int:
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    rid = _next_id("loop_run_id")
    get_collection("loop_runs").insert_one({
        "loop_run_id": rid,
        "loop_id": loop_id,
        "user_id": user_id,
        "workspace_id": scoped_workspace_id,
        "organization_id": organization_id,
        "status": "running",
        "jobs_discovered": 0,
        "jobs_qualified": 0,
        "applications_sent": 0,
        "applications_failed": 0,
        "budget_consumed": 0,
        "started_at": utc_now(),
        "completed_at": None,
        "error_message": None,
    })
    return rid


def update_loop_run(run_id: int, user_id: int, *, status: str = None, jobs_discovered: int = None, jobs_qualified: int = None, applications_sent: int = None, applications_failed: int = None, budget_consumed: int = None, error_message: str = None) -> None:
    updates: dict[str, Any] = {"updated_at": utc_now()}
    if status is not None:
        updates["status"] = status
        if status in ("completed", "failed", "cancelled"):
            updates["completed_at"] = utc_now()
    if jobs_discovered is not None:
        updates["jobs_discovered"] = jobs_discovered
    if jobs_qualified is not None:
        updates["jobs_qualified"] = jobs_qualified
    if applications_sent is not None:
        updates["applications_sent"] = applications_sent
    if applications_failed is not None:
        updates["applications_failed"] = applications_failed
    if budget_consumed is not None:
        updates["budget_consumed"] = budget_consumed
    if error_message is not None:
        updates["error_message"] = str(error_message)[:2000]

    if updates:
        get_collection("loop_runs").update_one(
            {"loop_run_id": run_id, "user_id": user_id},
            {"$set": updates},
        )


def list_loop_runs(loop_id: int, user_id: int, limit: int = 50, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("loop_runs").find(
        {"loop_id": loop_id, "user_id": user_id, "workspace_id": scoped_workspace_id}
    ).sort("started_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def get_loop_daily_usage(loop_id: int, user_id: int, workspace_id: int | None = None) -> int:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    today_start = utc_now()[:10] + "T00:00:00"
    pipeline = [
        {"$match": {
            "loop_id": loop_id,
            "user_id": user_id,
            "workspace_id": scoped_workspace_id,
            "started_at": {"$gte": today_start},
            "status": {"$in": ["completed", "running"]},
        }},
        {"$group": {"_id": None, "total": {"$sum": "$budget_consumed"}}},
    ]
    result = list(get_collection("loop_runs").aggregate(pipeline))
    return result[0]["total"] if result else 0


def get_active_loops(user_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("loops").find({
        "user_id": user_id,
        "workspace_id": scoped_workspace_id,
        "is_active": 1,
        "auto_apply_enabled": 1,
    })
    return [_format_loop(_strip_id(d)) for d in docs]


def _normalize_channels(channels: Any) -> list[str]:
    if not channels:
        return ["linkedin"]
    allowed = {"linkedin", "email", "ats_form"}
    return [c for c in channels if c in allowed] or ["linkedin"]


def _format_loop(doc: dict[str, Any]) -> dict[str, Any]:
    doc["is_active"] = bool(doc.get("is_active"))
    doc["auto_apply_enabled"] = bool(doc.get("auto_apply_enabled"))
    return doc
