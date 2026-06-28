from __future__ import annotations

import json
from typing import Any, Dict

import pymongo

from job_assistant.db.core import (
    _next_id, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
)

__all__ = [
    "FEEDBACK_CATEGORIES", "FEEDBACK_SEVERITIES", "FEEDBACK_STATUSES",
    "add_activity_event", "list_activity_events", "mark_activity_read",
    "create_feedback", "list_feedback", "get_feedback", "update_feedback_status",
    "list_audit_logs",
]

FEEDBACK_CATEGORIES = [
    "Bug Report", "Feature Request", "AI Quality Issue", "UI/UX Feedback",
    "Provider/API Problem", "Performance Issue", "Security Concern",
    "Automation Failure", "Integration Request", "General Suggestion",
]
FEEDBACK_SEVERITIES = ["low", "medium", "high", "critical"]
FEEDBACK_STATUSES = ["open", "triaged", "in_review", "planned", "in_progress", "resolved", "closed", "duplicate", "wont_fix"]


def add_activity_event(user_id: int, title: str, message: str = "", level: str = "info", metadata: Dict[str, Any] | None = None) -> None:
    eid = _next_id("activity_event_id")
    get_collection("activity_events").insert_one({
        "activity_event_id": eid, "user_id": user_id, "level": level,
        "title": title, "message": message,
        "metadata_json": json.dumps(metadata or {}),
        "created_at": utc_now(), "read_at": None,
    })


def list_activity_events(user_id: int, limit: int = 50, unread_only: bool = False) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"user_id": user_id}
    if unread_only:
        q["read_at"] = None
    docs = get_collection("activity_events").find(q).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def mark_activity_read(user_id: int) -> None:
    get_collection("activity_events").update_many(
        {"user_id": user_id, "read_at": None},
        {"$set": {"read_at": utc_now()}},
    )


def create_feedback(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    category = str(payload.get("category") or "General Suggestion").strip()
    if category not in FEEDBACK_CATEGORIES:
        category = "General Suggestion"
    severity = str(payload.get("severity") or "medium").strip().lower()
    if severity not in FEEDBACK_SEVERITIES:
        severity = "medium"
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    if not title or not description:
        raise ValueError("Feedback title and description are required")
    now = utc_now()
    metadata = payload.get("metadata") or {}
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id or payload.get("workspace_id"))
    fid = _next_id("feedback_id")
    get_collection("feedback").insert_one({
        "feedback_id": fid, "user_id": user_id, "workspace_id": scoped_workspace_id,
        "organization_id": organization_id, "category": category, "title": title,
        "description": description, "severity": severity,
        "status": str(payload.get("status") or "open"),
        "attachment_url": str(payload.get("attachment_url") or ""),
        "page_url": str(payload.get("page_url") or ""),
        "user_agent": str(payload.get("user_agent") or ""),
        "app_version": str(payload.get("app_version") or ""),
        "metadata_json": json.dumps(metadata), "created_at": now, "updated_at": now,
    })
    add_audit_log(user_id, "feedback.create", "feedback", str(fid), {"category": category, "severity": severity}, workspace_id=scoped_workspace_id, organization_id=organization_id)
    return fid


def list_feedback(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("feedback").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def get_feedback(feedback_id: int, user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    if workspace_id is None:
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    return _strip_id(doc) if doc else {}


def update_feedback_status(feedback_id: int, user_id: int, status: str, workspace_id: int | None = None) -> None:
    status = str(status or "").strip().lower()
    if status not in FEEDBACK_STATUSES:
        raise ValueError(f"Invalid feedback status: {status}")
    if workspace_id is None:
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    if not doc:
        raise ValueError("Feedback not found")
    get_collection("feedback").update_one(
        {"feedback_id": feedback_id, "user_id": user_id},
        {"$set": {"status": status, "updated_at": utc_now()}},
    )
    add_audit_log(user_id, "feedback.update_status", "feedback", str(feedback_id), {"status": status}, workspace_id=doc.get("workspace_id"), organization_id=doc.get("organization_id"))


def list_audit_logs(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    if workspace_id is None:
        docs = get_collection("audit_logs").find({"user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        docs = get_collection("audit_logs").find({"user_id": user_id, "workspace_id": scoped_workspace_id})
    docs = docs.sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]
