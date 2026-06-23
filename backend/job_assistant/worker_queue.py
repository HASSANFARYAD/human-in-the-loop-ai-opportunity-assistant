from __future__ import annotations

import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from job_assistant.config import settings
from job_assistant.db import _next_id, get_collection, utc_now

logger = logging.getLogger(__name__)


def enqueue_job(job_type: str, payload: dict[str, Any] | None = None, *, queue_name: str = "default", run_after: str = "") -> int:
    now = utc_now()
    job_id = _next_id("worker_job_id")
    get_collection("worker_jobs").insert_one({
        "_id": job_id,
        "queue_name": queue_name,
        "job_type": job_type,
        "payload_json": json.dumps(payload or {}),
        "status": "queued",
        "attempts": 0,
        "max_attempts": settings.worker_max_attempts,
        "run_after": run_after or now,
        "created_at": now,
        "updated_at": now,
    })
    return job_id


def list_worker_jobs(limit: int = 100, status: str = "") -> list[dict[str, Any]]:
    query = {}
    if status:
        query["status"] = status
    docs = get_collection("worker_jobs").find(query).sort("created_at", -1).limit(max(1, min(limit, 500)))
    out = []
    for doc in docs:
        doc.pop("_id", None)
        doc["payload"] = json.loads(doc.pop("payload_json") or "{}")
        out.append(doc)
    return out


def claim_next_job(queue_name: str = "default", worker_id: str = "") -> dict[str, Any] | None:
    worker = worker_id or socket.gethostname()
    now = utc_now()
    now_dt = datetime.now(timezone.utc)
    job = get_collection("worker_jobs").find_one_and_update(
        {
            "queue_name": queue_name,
            "status": "queued",
            "$expr": {
                "$lte": [
                    {"$ifNull": ["$run_after", "$created_at"]},
                    now,
                ]
            },
        },
        {
            "$set": {
                "status": "running",
                "locked_at": now,
                "locked_by": worker,
                "updated_at": now,
            },
            "$inc": {"attempts": 1},
        },
        sort=[("created_at", 1)],
        return_document=True,
    )
    if not job:
        return None
    job.pop("_id", None)
    job["payload"] = json.loads(job.pop("payload_json") or "{}")
    return job


def complete_job(job_id: int, result: dict[str, Any] | None = None) -> None:
    now = utc_now()
    get_collection("worker_jobs").update_one(
        {"_id": job_id},
        {"$set": {"status": "completed", "completed_at": now, "updated_at": now, "last_error": json.dumps(result or {})}},
    )


def fail_job(job_id: int, error: str) -> None:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat(timespec="seconds")
    job = get_collection("worker_jobs").find_one({"_id": job_id})
    if not job:
        return
    attempts = job.get("attempts", 0)
    max_attempts = job.get("max_attempts", settings.worker_max_attempts)
    if attempts >= max_attempts:
        get_collection("worker_jobs").update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "last_error": error[:1000], "updated_at": now}},
        )
    else:
        delay = min(60, 2 ** max(1, attempts))
        run_after = (now_dt + timedelta(seconds=delay)).isoformat(timespec="seconds")
        get_collection("worker_jobs").update_one(
            {"_id": job_id},
            {"$set": {"status": "queued", "run_after": run_after, "locked_at": None, "locked_by": None, "last_error": error[:1000], "updated_at": now}},
        )


def worker_health() -> dict[str, Any]:
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = list(get_collection("worker_jobs").aggregate(pipeline))
    queues = [{"status": r["_id"], "count": r["count"]} for r in rows]
    return {"status": "ok", "backend": settings.worker_backend, "queues": queues}
