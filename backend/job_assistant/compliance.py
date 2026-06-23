from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from job_assistant.config import settings
from job_assistant.db import _next_id, add_audit_log, delete_user_data, get_collection, utc_now


def _export_dir() -> Path:
    path = Path(settings.app_data_dir) / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


_USER_TABLES_MONGO = [
    ("users", False),
    ("profiles", True),
    ("jobs", True),
    ("feedback", True),
    ("audit_logs", True),
    ("integration_settings", True),
    ("provider_configs", True),
    ("ai_generations", True),
    ("automation_rules", True),
    ("automation_runs", True),
    ("posts", True),
]


def export_user_data(user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for table_name, has_user_id in _USER_TABLES_MONGO:
        coll = get_collection(table_name)
        if has_user_id:
            q: dict[str, Any] = {"user_id": user_id}
            if workspace_id:
                q["workspace_id"] = workspace_id
            docs = list(coll.find(q))
        elif table_name == "users":
            docs = list(coll.find({"user_id": user_id}, {"_id": 0, "password_hash": 0}))
        else:
            docs = []
        for d in docs:
            d.pop("_id", None)
            d.pop("password_hash", None)
        data[table_name] = docs
    expires_at = (datetime.now(timezone.utc) + timedelta(days=settings.export_retention_days)).isoformat(timespec="seconds")
    file_path = _export_dir() / f"user_{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    export_id = _next_id("compliance_export_id")
    get_collection("compliance_exports").insert_one({
        "_id": export_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "export_type": "user_data",
        "status": "completed",
        "file_path": str(file_path),
        "expires_at": expires_at,
        "created_at": utc_now(),
    })
    add_audit_log(user_id, "compliance.export", "compliance_export", str(export_id), {"file_path": str(file_path)}, workspace_id=workspace_id)
    return {"id": export_id, "file_path": str(file_path), "expires_at": expires_at}


def request_user_deletion(user_id: int, reason: str = "") -> int:
    alert_id = _next_id("alert_event_id")
    get_collection("alert_events").insert_one({
        "_id": alert_id,
        "severity": "critical",
        "title": "User deletion review requested",
        "message": reason or "User requested data deletion.",
        "source": "compliance",
        "metadata_json": json.dumps({"user_id": user_id}),
        "status": "open",
        "created_at": utc_now(),
    })
    add_audit_log(user_id, "compliance.deletion_requested", "user", str(user_id), {"alert_id": alert_id})
    return alert_id


def approve_user_deletion(admin_user_id: int, target_user_id: int) -> None:
    export_user_data(target_user_id)
    delete_user_data(target_user_id)
    add_audit_log(admin_user_id, "compliance.deletion_approved", "user", str(target_user_id), {})


def apply_retention_policies() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    audit_cutoff = (now - timedelta(days=settings.audit_retention_days)).isoformat(timespec="seconds")
    metrics_cutoff = (now - timedelta(days=settings.metrics_retention_days)).isoformat(timespec="seconds")
    export_cutoff = now.isoformat(timespec="seconds")
    counts = {"audit_logs": 0, "system_metrics": 0, "exports": 0}

    result = get_collection("audit_logs").delete_many({"created_at": {"$lt": audit_cutoff}})
    counts["audit_logs"] = result.deleted_count

    result = get_collection("system_metrics").delete_many({"created_at": {"$lt": metrics_cutoff}})
    counts["system_metrics"] = result.deleted_count

    expired = list(get_collection("compliance_exports").find({"expires_at": {"$lt": export_cutoff}}))
    for row in expired:
        try:
            Path(row["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    result = get_collection("compliance_exports").delete_many({"expires_at": {"$lt": export_cutoff}})
    counts["exports"] = result.deleted_count
    return counts


def list_compliance_exports(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    docs = list(get_collection("compliance_exports").find({"user_id": user_id}).sort("created_at", -1).limit(max(1, min(limit, 500))))
    for d in docs:
        d.pop("_id", None)
    return docs


def admin_review(limit: int = 100) -> dict[str, Any]:
    alerts = list(get_collection("alert_events").find().sort("created_at", -1).limit(max(1, min(limit, 500))))
    audits = list(get_collection("audit_logs").find().sort("created_at", -1).limit(max(1, min(limit, 500))))
    for d in alerts:
        d.pop("_id", None)
    for d in audits:
        d.pop("_id", None)
    return {"alerts": alerts, "audit_logs": audits}
