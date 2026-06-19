from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from job_assistant.config import settings
from job_assistant.db import add_audit_log, connect, delete_user_data, utc_now


def _export_dir() -> Path:
    path = Path(settings.app_data_dir) / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_user_data(user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    with connect() as con:
        tables = [
            "users",
            "profile",
            "jobs",
            "feedback",
            "audit_logs",
            "integration_settings",
            "provider_configs",
            "ai_generations",
            "automation_rules",
            "automation_runs",
            "posts",
        ]
        for table in tables:
            cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
            if "user_id" in cols:
                if workspace_id and "workspace_id" in cols:
                    rows = con.execute(f"SELECT * FROM {table} WHERE user_id=? AND workspace_id=?", (user_id, workspace_id)).fetchall()
                else:
                    rows = con.execute(f"SELECT * FROM {table} WHERE user_id=?", (user_id,)).fetchall()
            elif table == "users":
                rows = con.execute("SELECT id, email, full_name, is_active, created_at, updated_at FROM users WHERE id=?", (user_id,)).fetchall()
            else:
                rows = []
            data[table] = [dict(row) for row in rows]
        expires_at = (datetime.now(timezone.utc) + timedelta(days=settings.export_retention_days)).isoformat(timespec="seconds")
        file_path = _export_dir() / f"user_{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
        file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        cur = con.execute(
            "INSERT INTO compliance_exports(user_id, workspace_id, export_type, status, file_path, expires_at, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, workspace_id, "user_data", "completed", str(file_path), expires_at, utc_now()),
        )
        export_id = int(cur.lastrowid)
        add_audit_log(user_id, "compliance.export", "compliance_export", str(export_id), {"file_path": str(file_path)}, con=con, workspace_id=workspace_id)
    return {"id": export_id, "file_path": str(file_path), "expires_at": expires_at}


def request_user_deletion(user_id: int, reason: str = "") -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO alert_events(severity, title, message, source, metadata_json, status, created_at) VALUES (?,?,?,?,?,?,?)",
            ("critical", "User deletion review requested", reason or "User requested data deletion.", "compliance", json.dumps({"user_id": user_id}), "open", utc_now()),
        )
        alert_id = int(cur.lastrowid)
        add_audit_log(user_id, "compliance.deletion_requested", "user", str(user_id), {"alert_id": alert_id}, con=con)
        return alert_id


def approve_user_deletion(admin_user_id: int, target_user_id: int) -> None:
    export_user_data(target_user_id)
    delete_user_data(target_user_id)
    with connect() as con:
        add_audit_log(admin_user_id, "compliance.deletion_approved", "user", str(target_user_id), {}, con=con)


def apply_retention_policies() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    audit_cutoff = (now - timedelta(days=settings.audit_retention_days)).isoformat(timespec="seconds")
    metrics_cutoff = (now - timedelta(days=settings.metrics_retention_days)).isoformat(timespec="seconds")
    export_cutoff = now.isoformat(timespec="seconds")
    counts = {"audit_logs": 0, "system_metrics": 0, "exports": 0}
    with connect() as con:
        counts["audit_logs"] = con.execute("DELETE FROM audit_logs WHERE created_at < ?", (audit_cutoff,)).rowcount
        counts["system_metrics"] = con.execute("DELETE FROM system_metrics WHERE created_at < ?", (metrics_cutoff,)).rowcount
        expired = con.execute("SELECT id, file_path FROM compliance_exports WHERE expires_at < ?", (export_cutoff,)).fetchall()
        for row in expired:
            try:
                Path(row["file_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        counts["exports"] = con.execute("DELETE FROM compliance_exports WHERE expires_at < ?", (export_cutoff,)).rowcount
    return counts


def list_compliance_exports(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute("SELECT * FROM compliance_exports WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, max(1, min(limit, 500)))).fetchall()
    return [dict(row) for row in rows]


def admin_review(limit: int = 100) -> dict[str, Any]:
    with connect() as con:
        alerts = con.execute("SELECT * FROM alert_events ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        audits = con.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return {"alerts": [dict(row) for row in alerts], "audit_logs": [dict(row) for row in audits]}
