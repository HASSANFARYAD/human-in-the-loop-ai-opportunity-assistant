from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from starlette.responses import Response

from job_assistant.config import settings
from job_assistant.db import connect, utc_now

logger = logging.getLogger(__name__)


def _labels(labels: dict[str, Any] | None = None) -> str:
    return json.dumps(labels or {}, sort_keys=True)


def record_metric(metric_name: str, value: float = 1, metric_type: str = "counter", labels: dict[str, Any] | None = None) -> None:
    if not settings.observability_enabled:
        return
    try:
        with connect() as con:
            con.execute(
                "INSERT INTO system_metrics(metric_name, metric_type, value, labels_json, created_at) VALUES (?,?,?,?,?)",
                (metric_name, metric_type, float(value), _labels(labels), utc_now()),
            )
    except Exception as exc:
        logger.debug("Failed to record metric %s: %s", metric_name, exc)


def create_alert(severity: str, title: str, message: str = "", source: str = "system", metadata: dict[str, Any] | None = None) -> None:
    try:
        with connect() as con:
            con.execute(
                "INSERT INTO alert_events(severity, title, message, source, metadata_json, status, created_at) VALUES (?,?,?,?,?,?,?)",
                (severity, title, message, source, json.dumps(metadata or {}), "open", utc_now()),
            )
    except Exception as exc:
        logger.debug("Failed to create alert %s: %s", title, exc)


async def observability_middleware(request: Request, call_next):
    if not settings.observability_enabled or not request.url.path.startswith("/api/"):
        return await call_next(request)
    trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        record_metric("api_errors_total", 1, labels={"path": request.url.path, "method": request.method})
        raise
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        labels = {"path": request.url.path, "method": request.method, "status": status_code}
        record_metric("api_requests_total", 1, labels=labels)
        record_metric("api_request_latency_ms", latency_ms, metric_type="histogram", labels=labels)
        if latency_ms >= settings.latency_alert_threshold_ms:
            create_alert("warning", "Slow API request", f"{request.method} {request.url.path} took {latency_ms} ms", "observability", {"trace_id": trace_id})
        if status_code >= 500:
            create_alert("critical", "API server error", f"{request.method} {request.url.path} returned {status_code}", "observability", {"trace_id": trace_id})
        try:
            response.headers["X-Trace-ID"] = trace_id
        except Exception:
            pass


def metrics_summary(hours: int = 24) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with connect() as con:
        metrics = con.execute(
            """
            SELECT metric_name, metric_type, COUNT(*) AS samples, SUM(value) AS total, AVG(value) AS avg_value, MAX(value) AS max_value
            FROM system_metrics
            WHERE created_at >= ?
            GROUP BY metric_name, metric_type
            ORDER BY metric_name
            """,
            (cutoff,),
        ).fetchall()
        alerts = con.execute("SELECT * FROM alert_events WHERE status='open' ORDER BY created_at DESC LIMIT 50").fetchall()
    return {"status": "ok", "window_hours": hours, "metrics": [dict(r) for r in metrics], "open_alerts": [dict(r) for r in alerts]}


def prometheus_text() -> Response:
    with connect() as con:
        rows = con.execute(
            """
            SELECT metric_name, SUM(value) AS value
            FROM system_metrics
            GROUP BY metric_name
            ORDER BY metric_name
            """
        ).fetchall()
    lines = ["# HELP job_assistant_local_metrics Local SQLite-backed metrics", "# TYPE job_assistant_local_metrics gauge"]
    for row in rows:
        name = str(row["metric_name"]).replace("-", "_").replace(".", "_")
        lines.append(f"job_assistant_{name} {float(row['value'] or 0)}")
    return Response("\n".join(lines) + "\n", media_type="text/plain")


def acknowledge_alert(alert_id: int) -> bool:
    with connect() as con:
        cur = con.execute("UPDATE alert_events SET status='acknowledged', acknowledged_at=? WHERE id=?", (utc_now(), alert_id))
        return cur.rowcount > 0
