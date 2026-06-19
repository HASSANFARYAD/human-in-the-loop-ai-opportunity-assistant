from __future__ import annotations

import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from job_assistant.config import settings
from job_assistant.db import connect, utc_now

logger = logging.getLogger(__name__)


def enqueue_job(job_type: str, payload: dict[str, Any] | None = None, *, queue_name: str = "default", run_after: str = "") -> int:
    now = utc_now()
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO worker_jobs(queue_name, job_type, payload_json, status, attempts, max_attempts, run_after, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (queue_name, job_type, json.dumps(payload or {}), "queued", 0, settings.worker_max_attempts, run_after or now, now, now),
        )
        return int(cur.lastrowid)


def list_worker_jobs(limit: int = 100, status: str = "") -> list[dict[str, Any]]:
    with connect() as con:
        if status:
            rows = con.execute("SELECT * FROM worker_jobs WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, max(1, min(limit, 500)))).fetchall()
        else:
            rows = con.execute("SELECT * FROM worker_jobs ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out


def claim_next_job(queue_name: str = "default", worker_id: str = "") -> dict[str, Any] | None:
    worker = worker_id or socket.gethostname()
    now = utc_now()
    with connect() as con:
        row = con.execute(
            """
            SELECT * FROM worker_jobs
            WHERE queue_name=? AND status='queued' AND COALESCE(run_after, created_at) <= ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (queue_name, now),
        ).fetchone()
        if not row:
            return None
        con.execute(
            "UPDATE worker_jobs SET status='running', locked_at=?, locked_by=?, attempts=attempts+1, updated_at=? WHERE id=? AND status='queued'",
            (now, worker, now, row["id"]),
        )
        claimed = con.execute("SELECT * FROM worker_jobs WHERE id=?", (row["id"],)).fetchone()
    if not claimed:
        return None
    item = dict(claimed)
    item["payload"] = json.loads(item.pop("payload_json") or "{}")
    return item


def complete_job(job_id: int, result: dict[str, Any] | None = None) -> None:
    now = utc_now()
    with connect() as con:
        con.execute(
            "UPDATE worker_jobs SET status='completed', completed_at=?, updated_at=?, last_error=? WHERE id=?",
            (now, now, json.dumps(result or {}), job_id),
        )


def fail_job(job_id: int, error: str) -> None:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat(timespec="seconds")
    with connect() as con:
        row = con.execute("SELECT attempts, max_attempts FROM worker_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return
        if int(row["attempts"] or 0) >= int(row["max_attempts"] or settings.worker_max_attempts):
            con.execute("UPDATE worker_jobs SET status='failed', last_error=?, updated_at=? WHERE id=?", (error[:1000], now, job_id))
        else:
            delay = min(60, 2 ** max(1, int(row["attempts"] or 1)))
            run_after = (now_dt + timedelta(seconds=delay)).isoformat(timespec="seconds")
            con.execute(
                "UPDATE worker_jobs SET status='queued', run_after=?, locked_at=NULL, locked_by=NULL, last_error=?, updated_at=? WHERE id=?",
                (run_after, error[:1000], now, job_id),
            )


def worker_health() -> dict[str, Any]:
    with connect() as con:
        rows = con.execute("SELECT status, COUNT(*) AS count FROM worker_jobs GROUP BY status").fetchall()
    return {"status": "ok", "backend": settings.worker_backend, "queues": [dict(r) for r in rows]}
