from __future__ import annotations

import json
from typing import Any, Dict

import pymongo

from job_assistant.db.core import (
    _next_id, _safe_json_loads, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
)

__all__ = [
    "get_automation_preferences", "save_automation_preferences",
    "create_automation_rule", "list_automation_rules",
    "update_automation_rule", "delete_automation_rule",
    "create_automation_run", "update_automation_run",
    "list_automation_runs", "add_automation_error", "list_automation_errors",
]


def get_automation_preferences(user_id: int) -> dict[str, Any]:
    doc = get_collection("automation_preferences").find_one({"user_id": user_id})
    if doc:
        data = _strip_id(doc)
    else:
        data = {
            "user_id": user_id, "enabled": 0, "gmail_enabled": 1,
            "public_sources_enabled": 1, "linkedin_api_enabled": 0,
            "score_new": 1, "generate_materials": 0,
            "gmail_interval_minutes": 30, "public_interval_hours": 6,
            "linkedin_interval_hours": 6, "daily_summary_hour": 8,
            "notify_in_app": 1, "min_score_for_materials": 70,
            "updated_at": utc_now(),
        }
    for key in ["enabled", "gmail_enabled", "public_sources_enabled", "linkedin_api_enabled", "score_new", "generate_materials", "notify_in_app"]:
        data[key] = bool(data.get(key))
    return data


def save_automation_preferences(user_id: int, prefs: Dict[str, Any]) -> None:
    current = get_automation_preferences(user_id)
    current.update(prefs or {})
    fields = [
        "enabled", "gmail_enabled", "public_sources_enabled", "linkedin_api_enabled",
        "score_new", "generate_materials", "gmail_interval_minutes",
        "public_interval_hours", "linkedin_interval_hours", "daily_summary_hour",
        "notify_in_app", "min_score_for_materials",
    ]
    values = {k: int(current[k]) if isinstance(current[k], bool) else current[k] for k in fields}
    values["updated_at"] = utc_now()
    get_collection("automation_preferences").update_one(
        {"user_id": user_id},
        {"$set": values},
        upsert=True,
    )


def create_automation_rule(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    now = utc_now()
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id or payload.get("workspace_id"))
    rid = _next_id("automation_rule_id")
    get_collection("automation_rules").insert_one({
        "automation_rule_id": rid, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "name": str(payload.get("name") or "Automation rule"),
        "trigger_event": str(payload.get("trigger_event") or "manual"),
        "action_type": str(payload.get("action_type") or "notify"),
        "conditions_json": json.dumps(payload.get("conditions") or {}),
        "action_config_json": json.dumps(payload.get("action_config") or {}),
        "is_active": 1 if payload.get("is_active", True) else 0,
        "human_approval_required": 1 if payload.get("human_approval_required", True) else 0,
        "created_at": now, "updated_at": now,
    })
    add_audit_log(user_id, "automation_rule.create", "automation_rule", str(rid), {"trigger_event": payload.get("trigger_event"), "action_type": payload.get("action_type")}, workspace_id=scoped_workspace_id, organization_id=organization_id)
    return rid


def list_automation_rules(user_id: int, include_inactive: bool = False, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    q: dict[str, Any] = {"user_id": user_id, "workspace_id": scoped_workspace_id}
    if not include_inactive:
        q["is_active"] = 1
    docs = get_collection("automation_rules").find(q).sort("created_at", pymongo.DESCENDING)
    out = []
    for doc in docs:
        item = _strip_id(doc)
        item["conditions"] = _safe_json_loads(item.pop("conditions_json", "{}"), {})
        item["action_config"] = _safe_json_loads(item.pop("action_config_json", "{}"), {})
        item["is_active"] = bool(item.get("is_active"))
        item["human_approval_required"] = bool(item.get("human_approval_required"))
        out.append(item)
    return out


def update_automation_rule(rule_id: int, user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> None:
    current = next((r for r in list_automation_rules(user_id, include_inactive=True, workspace_id=workspace_id) if int(r["automation_rule_id"]) == int(rule_id)), None)
    if not current:
        raise ValueError("Automation rule not found")
    merged = {**current, **(payload or {})}
    get_collection("automation_rules").update_one(
        {"automation_rule_id": rule_id, "user_id": user_id, "workspace_id": current["workspace_id"]},
        {"$set": {
            "name": str(merged.get("name") or current["name"]),
            "trigger_event": str(merged.get("trigger_event") or current["trigger_event"]),
            "action_type": str(merged.get("action_type") or current["action_type"]),
            "conditions_json": json.dumps(merged.get("conditions") or {}),
            "action_config_json": json.dumps(merged.get("action_config") or {}),
            "is_active": 1 if merged.get("is_active", True) else 0,
            "human_approval_required": 1 if merged.get("human_approval_required", True) else 0,
            "updated_at": utc_now(),
        }},
    )
    add_audit_log(user_id, "automation_rule.update", "automation_rule", str(rule_id), {}, workspace_id=current["workspace_id"], organization_id=current.get("organization_id"))


def delete_automation_rule(rule_id: int, user_id: int, workspace_id: int | None = None) -> None:
    current = next((r for r in list_automation_rules(user_id, include_inactive=True, workspace_id=workspace_id) if int(r["automation_rule_id"]) == int(rule_id)), None)
    if current:
        get_collection("automation_rules").delete_one({"automation_rule_id": rule_id, "user_id": user_id, "workspace_id": current["workspace_id"]})
        add_audit_log(user_id, "automation_rule.delete", "automation_rule", str(rule_id), {}, workspace_id=current["workspace_id"], organization_id=current.get("organization_id"))


def create_automation_run(user_id: int, trigger_event: str, input_payload: Dict[str, Any] | None = None, rule_id: int | None = None, status: str = "pending", workspace_id: int | None = None) -> int:
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    rid = _next_id("automation_run_id")
    get_collection("automation_runs").insert_one({
        "automation_run_id": rid, "rule_id": rule_id, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "status": status, "trigger_event": trigger_event,
        "input_payload": json.dumps(input_payload or {}),
        "created_at": utc_now(),
    })
    return rid


def update_automation_run(run_id: int, user_id: int, *, status: str, output_payload: Dict[str, Any] | None = None, error_message: str = "") -> None:
    now = utc_now()
    completed = now if status in {"completed", "failed", "cancelled", "requires_approval"} else None
    update: dict[str, Any] = {
        "status": status, "output_payload": json.dumps(output_payload or {}),
        "error_message": error_message, "updated_at": now,
    }
    if completed:
        update["completed_at"] = completed
    get_collection("automation_runs").update_one(
        {"automation_run_id": run_id, "user_id": user_id},
        {"$set": update, "$setOnInsert": {"started_at": now}},
    )


def list_automation_runs(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("automation_runs").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    out = []
    for doc in docs:
        item = _strip_id(doc)
        item["input_payload"] = _safe_json_loads(item.get("input_payload"), {})
        item["output_payload"] = _safe_json_loads(item.get("output_payload"), {})
        out.append(item)
    return out


def add_automation_error(user_id: int | None, run_id: int | None, error_message: str, error_type: str = "runtime", metadata: Dict[str, Any] | None = None, workspace_id: int | None = None) -> None:
    scoped_workspace_id = None
    organization_id = None
    if run_id:
        run = get_collection("automation_runs").find_one({"automation_run_id": run_id})
        if run:
            scoped_workspace_id, organization_id = run.get("workspace_id"), run.get("organization_id")
    elif user_id:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    aid = _next_id("automation_error_id")
    get_collection("automation_errors").insert_one({
        "automation_error_id": aid, "run_id": run_id, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "error_type": error_type, "error_message": error_message,
        "metadata_json": json.dumps(metadata or {}),
        "created_at": utc_now(),
    })


def list_automation_errors(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("automation_errors").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]
