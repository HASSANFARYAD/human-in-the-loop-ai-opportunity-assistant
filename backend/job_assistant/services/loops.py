from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from job_assistant.db import (
    get_loop, list_loops, get_active_loops, get_loop_daily_usage,
    create_loop_run, update_loop_run, list_loop_runs,
    update_loop, get_loop,
    get_collection, utc_now,
)
from job_assistant.services.auto_apply_pipeline import execute_auto_apply_pipeline

logger = logging.getLogger(__name__)


def execute_loop(loop_id: int, user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    loop = get_loop(loop_id, user_id, workspace_id=workspace_id)
    if not loop:
        raise ValueError(f"Loop {loop_id} not found")
    if not loop.get("is_active"):
        raise ValueError(f"Loop {loop_id} is inactive")

    auto_apply_enabled = loop.get("auto_apply_enabled", False)
    daily_budget = loop.get("daily_budget", 10)
    current_usage = 0

    if auto_apply_enabled:
        current_usage = get_loop_daily_usage(loop_id, user_id, workspace_id=workspace_id)
        remaining = daily_budget - current_usage
        if remaining <= 0:
            logger.info("Loop %d: daily budget exhausted (%d/%d)", loop_id, current_usage, daily_budget)
            return {
                "loop_id": loop_id,
                "status": "budget_exhausted",
                "message": f"Daily budget exhausted ({current_usage}/{daily_budget})",
            }

    run_id = create_loop_run(loop_id, user_id, workspace_id=workspace_id)

    try:
        pipeline_result = execute_auto_apply_pipeline(
            user_id=user_id,
            workspace_id=workspace_id,
            query=loop.get("search_query", ""),
            sources=loop.get("sources", []),
            platforms=loop.get("platforms", ["linkedin"]),
            channels=loop.get("channels", ["linkedin"]),
            min_score=loop.get("min_score_threshold", 60),
            max_applications=min(
                loop.get("max_applications_per_run", 5),
                remaining if auto_apply_enabled else 999,
            ),
            dry_run=True,
            loop_id=loop_id,
            run_id=run_id,
        )

        update_loop_run(
            run_id, user_id,
            status="completed",
            jobs_discovered=pipeline_result.get("jobs_discovered", 0),
            jobs_qualified=pipeline_result.get("jobs_qualified", 0),
            applications_sent=pipeline_result.get("applications_submitted", 0),
            applications_failed=pipeline_result.get("applications_failed", 0),
            budget_consumed=pipeline_result.get("budget_consumed", 0),
        )

        update_loop(loop_id, user_id, {"last_run_at": utc_now()}, workspace_id=workspace_id)

        logger.info(
            "Loop %d completed: discovered=%d, qualified=%d, sent=%d, failed=%d, budget=%d",
            loop_id,
            pipeline_result.get("jobs_discovered", 0),
            pipeline_result.get("jobs_qualified", 0),
            pipeline_result.get("applications_submitted", 0),
            pipeline_result.get("applications_failed", 0),
            pipeline_result.get("budget_consumed", 0),
        )

        return {
            "loop_id": loop_id,
            "run_id": run_id,
            "status": "completed",
            **pipeline_result,
        }

    except Exception as e:
        logger.error("Loop %d execution failed: %s", loop_id, e)
        update_loop_run(run_id, user_id, status="failed", error_message=str(e))
        return {"loop_id": loop_id, "run_id": run_id, "status": "failed", "error": str(e)}


def check_and_run_due_loops(user_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
    active_loops = get_active_loops(user_id, workspace_id=workspace_id)
    results = []
    now = datetime.now(timezone.utc)

    for loop in active_loops:
        last_run = loop.get("last_run_at")
        interval = loop.get("schedule_interval_hours", 6)
        if last_run:
            last_dt = datetime.fromisoformat(last_run)
            if now - last_dt < timedelta(hours=interval):
                continue
        try:
            result = execute_loop(int(loop["loop_id"]), user_id, workspace_id=workspace_id)
            results.append(result)
        except Exception as e:
            logger.error("Failed to run loop %s: %s", loop.get("loop_id"), e)
            results.append({"loop_id": loop.get("loop_id"), "status": "error", "error": str(e)})

    return results


def get_loop_status(loop_id: int, user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    loop = get_loop(loop_id, user_id, workspace_id=workspace_id)
    if not loop:
        raise ValueError(f"Loop {loop_id} not found")

    daily_usage = get_loop_daily_usage(loop_id, user_id, workspace_id=workspace_id)
    recent_runs = list_loop_runs(loop_id, user_id, limit=5, workspace_id=workspace_id)

    return {
        "loop": loop,
        "daily_usage": daily_usage,
        "daily_budget": loop.get("daily_budget", 10),
        "budget_remaining": max(0, loop.get("daily_budget", 10) - daily_usage),
        "recent_runs": recent_runs,
    }
