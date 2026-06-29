from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from job_assistant.auth import current_user
from job_assistant.config import settings
from job_assistant.db import (
    ai_usage_detailed,
    count_ai_generations_today,
    ensure_user_workspace,
    get_rate_limit_status,
    usage_summary,
    user_has_permission,
)
from job_assistant.observability import acknowledge_alert, metrics_summary, prometheus_text
from job_assistant.worker_queue import enqueue_job, list_worker_jobs, worker_health

logger = logging.getLogger(__name__)

router = APIRouter()


class WorkerJobIn(BaseModel):
    queue_name: str = "default"
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    run_after: str = ""


def _require_workspace_admin(user: dict, workspace_id: int | None = None) -> None:
    workspace = ensure_user_workspace(user["id"])
    scoped_workspace_id = int(workspace_id or workspace.get("workspace_id") or 0)
    role = str(workspace.get("role") or "owner").lower()
    if role in {"owner", "admin"}:
        return
    if scoped_workspace_id and user_has_permission(user["id"], scoped_workspace_id, "workspace:manage"):
        return
    raise HTTPException(status_code=403, detail="Workspace administrator access is required.")


@router.get("/usage")
async def get_usage(user: dict = Depends(current_user)):
    return {"status": "ok", "usage": usage_summary(user["id"])}


@router.get("/observability")
async def get_observability(hours: int = 24, user: dict = Depends(current_user)):
    return metrics_summary(hours=hours)


@router.get("/metrics")
async def get_prometheus_metrics():
    return prometheus_text()


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return {"status": "success" if acknowledge_alert(alert_id) else "not_found"}


@router.get("/workers/health")
async def get_worker_health(user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return worker_health()


@router.get("/workers/jobs")
async def get_worker_jobs(limit: int = 100, status: str = "", user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return list_worker_jobs(limit=limit, status=status)


@router.post("/workers/jobs")
async def post_worker_job(payload: WorkerJobIn, user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    job_id = enqueue_job(payload.job_type, payload.payload, queue_name=payload.queue_name, run_after=payload.run_after)
    return {"id": job_id, "status": "queued"}


@router.get("/rate-limits")
async def rate_limits(user: dict = Depends(current_user)):
    return {"rate_limits": get_rate_limit_status()}
