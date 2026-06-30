from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from job_assistant.auth import current_user
from job_assistant.db import (
    create_loop, get_loop, list_loops, update_loop, delete_loop,
    list_loop_runs, get_loop_daily_usage,
    list_auto_apply_logs, get_auto_apply_stats, get_daily_apply_count,
    get_pending_approval_logs,
)
from job_assistant.services.loops import execute_loop, get_loop_status
from job_assistant.services.multi_source_discovery import get_circuit_breaker_stats, reset_circuit_breaker

logger = logging.getLogger(__name__)

router = APIRouter()


class LoopCreate(BaseModel):
    workspace_id: Optional[int] = None
    name: str = "Untitled Loop"
    search_query: str = ""
    sources: list[str] = Field(default_factory=lambda: ["LinkedIn", "RemoteJobs.org", "Arbeitnow"])
    platforms: list[str] = Field(default_factory=lambda: ["linkedin", "email"])
    is_active: bool = True
    auto_apply_enabled: bool = False
    daily_budget: int = 10
    max_applications_per_run: int = 5
    min_score_threshold: int = 60
    channels: list[str] = Field(default_factory=lambda: ["linkedin"])
    schedule_interval_hours: int = 6


class LoopUpdate(BaseModel):
    workspace_id: Optional[int] = None
    name: Optional[str] = None
    search_query: Optional[str] = None
    sources: Optional[list[str]] = None
    platforms: Optional[list[str]] = None
    is_active: Optional[bool] = None
    auto_apply_enabled: Optional[bool] = None
    daily_budget: Optional[int] = None
    max_applications_per_run: Optional[int] = None
    min_score_threshold: Optional[int] = None
    channels: Optional[list[str]] = None
    schedule_interval_hours: Optional[int] = None


class LoopRunRequest(BaseModel):
    workspace_id: Optional[int] = None


@router.get("/loops")
async def list_loops_endpoint(include_inactive: bool = False, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_loops(user["id"], include_inactive=include_inactive, workspace_id=workspace_id)


@router.post("/loops")
async def create_loop_endpoint(payload: LoopCreate, user: dict = Depends(current_user)):
    loop_id = create_loop(user["id"], payload.model_dump(), workspace_id=payload.workspace_id)
    return {"id": loop_id, "status": "success"}


@router.get("/loops/{loop_id}")
async def get_loop_endpoint(loop_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    loop = get_loop(loop_id, user["id"], workspace_id=workspace_id)
    if not loop:
        raise HTTPException(status_code=404, detail="Loop not found")
    return loop


@router.put("/loops/{loop_id}")
async def update_loop_endpoint(loop_id: int, payload: LoopUpdate, user: dict = Depends(current_user)):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        updated = update_loop(loop_id, user["id"], data, workspace_id=payload.workspace_id)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/loops/{loop_id}")
async def delete_loop_endpoint(loop_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        delete_loop(loop_id, user["id"], workspace_id=workspace_id)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/loops/{loop_id}/run")
async def run_loop_endpoint(loop_id: int, payload: LoopRunRequest, user: dict = Depends(current_user)):
    try:
        result = execute_loop(loop_id, user["id"], workspace_id=payload.workspace_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/loops/{loop_id}/status")
async def loop_status_endpoint(loop_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        return get_loop_status(loop_id, user["id"], workspace_id=workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/loops/{loop_id}/runs")
async def loop_runs_endpoint(loop_id: int, limit: int = 50, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_loop_runs(loop_id, user["id"], limit=limit, workspace_id=workspace_id)


@router.get("/auto-apply/logs")
async def auto_apply_logs_endpoint(limit: int = 100, status: Optional[str] = None, loop_id: Optional[int] = None, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_auto_apply_logs(user["id"], limit=limit, status=status, loop_id=loop_id, workspace_id=workspace_id)


@router.get("/auto-apply/stats")
async def auto_apply_stats_endpoint(days: int = 30, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return get_auto_apply_stats(user["id"], workspace_id=workspace_id, days=days)


@router.get("/auto-apply/daily-count")
async def daily_apply_count_endpoint(workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return {"count": get_daily_apply_count(user["id"], workspace_id=workspace_id)}


@router.get("/auto-apply/pending-approval")
async def pending_approval_endpoint(limit: int = 50, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return get_pending_approval_logs(user["id"], workspace_id=workspace_id, limit=limit)


@router.get("/auto-apply/health")
async def auto_apply_health_endpoint(user: dict = Depends(current_user)):
    user_id = user["id"]
    now = datetime.now(timezone.utc)

    circuit_breaker = get_circuit_breaker_stats()
    open_sources = [s for s in circuit_breaker if s.get("circuit_open")]
    degraded_sources = [s for s in circuit_breaker if s.get("consecutive_failures", 0) > 0 and not s.get("circuit_open")]

    loops = list_loops(user_id)
    active_loops = [l for l in loops if l.get("is_active")]
    total_daily_budget = sum(l.get("daily_budget", 0) or 0 for l in active_loops)
    total_daily_usage = sum(get_loop_daily_usage(l["loop_id"]) for l in active_loops)

    recent_runs = []
    for l in loops[:10]:
        recent_runs.extend(list_loop_runs(l["loop_id"], user_id, limit=5))
    recent_runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    recent_runs = recent_runs[:20]
    total_runs = len(recent_runs)
    failed_runs = [r for r in recent_runs if r.get("status") == "failed"]
    error_runs = [r for r in recent_runs if r.get("status") == "error"]
    success_runs = [r for r in recent_runs if r.get("status") == "completed"]

    auto_apply_stats = get_auto_apply_stats(user_id, days=7)
    daily_count = get_daily_apply_count(user_id)

    warnings = []

    if open_sources:
        warnings.append(f"Circuit breaker open for {len(open_sources)} source(s): {', '.join(s['source'] for s in open_sources)}")
    if failed_runs or error_runs:
        warnings.append(f"{len(failed_runs) + len(error_runs)} of last {total_runs or 1} loop runs had errors")

    if total_daily_budget > 0 and total_daily_usage >= total_daily_budget:
        warnings.append("Daily budget exhausted across all active loops")

    if total_runs == 0:
        status = "inactive"
    elif open_sources and len(open_sources) >= 3:
        status = "unhealthy"
    elif warnings:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "timestamp": now.isoformat(),
        "warnings": warnings,
        "circuit_breaker": {
            "total_sources": len(circuit_breaker),
            "open": len(open_sources),
            "degraded": len(degraded_sources),
            "open_sources": [{"source": s["source"], "cooldown_remaining_s": s.get("cooldown_remaining", 0)} for s in open_sources],
            "degraded_sources": [{"source": s["source"], "failures": s.get("consecutive_failures", 0)} for s in degraded_sources],
        },
        "loops": {
            "total": len(loops),
            "active": len(active_loops),
            "today_budget": total_daily_budget,
            "today_usage": total_daily_usage,
            "budget_remaining": max(0, total_daily_budget - total_daily_usage),
        },
        "runs": {
            "total_last_7d": total_runs,
            "success": len(success_runs),
            "failed": len(failed_runs),
            "errors": len(error_runs),
            "success_rate_pct": round((len(success_runs) / max(total_runs, 1)) * 100, 1),
        },
        "auto_apply": {
            "applications_today": daily_count,
            "stats_7d": auto_apply_stats,
        },
    }


@router.post("/auto-apply/health/reset-circuit-breaker")
async def reset_circuit_breaker_endpoint(source: str | None = None, user: dict = Depends(current_user)):
    reset_circuit_breaker(source)
    return {"status": "ok", "message": f"Circuit breaker reset for {'all sources' if not source else source}"}
