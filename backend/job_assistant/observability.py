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
from job_assistant.db import _next_id, get_collection, utc_now

logger = logging.getLogger(__name__)

METRICS_COLL = "system_metrics"
ALERTS_COLL = "alert_events"


def _labels(labels: dict[str, Any] | None = None) -> str:
    return json.dumps(labels or {}, sort_keys=True)


def record_metric(metric_name: str, value: float = 1, metric_type: str = "counter", labels: dict[str, Any] | None = None) -> None:
    if not settings.observability_enabled:
        return
    try:
        get_collection(METRICS_COLL).insert_one({
            "metric_name": metric_name,
            "metric_type": metric_type,
            "value": float(value),
            "labels_json": _labels(labels),
            "created_at": utc_now(),
        })
    except Exception as exc:
        logger.debug("Failed to record metric %s: %s", metric_name, exc)


def create_alert(severity: str, title: str, message: str = "", source: str = "system", metadata: dict[str, Any] | None = None) -> None:
    try:
        alert_id = _next_id("alert_event_id")
        get_collection(ALERTS_COLL).insert_one({
            "_id": alert_id,
            "severity": severity,
            "title": title,
            "message": message,
            "source": source,
            "metadata_json": json.dumps(metadata or {}),
            "status": "open",
            "created_at": utc_now(),
        })
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
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"metric_name": "$metric_name", "metric_type": "$metric_type"},
            "samples": {"$sum": 1},
            "total": {"$sum": "$value"},
            "avg_value": {"$avg": "$value"},
            "max_value": {"$max": "$value"},
        }},
        {"$sort": {"_id.metric_name": 1}},
    ]
    metrics = list(get_collection(METRICS_COLL).aggregate(pipeline))
    output_metrics = []
    for m in metrics:
        output_metrics.append({
            "metric_name": m["_id"]["metric_name"],
            "metric_type": m["_id"]["metric_type"],
            "samples": m["samples"],
            "total": m["total"],
            "avg_value": m["avg_value"],
            "max_value": m["max_value"],
        })
    alerts = list(get_collection(ALERTS_COLL).find({"status": "open"}).sort("created_at", -1).limit(50))
    return {"status": "ok", "window_hours": hours, "metrics": output_metrics, "open_alerts": alerts}


def prometheus_text() -> Response:
    pipeline = [
        {"$group": {"_id": "$metric_name", "total": {"$sum": "$value"}}},
        {"$sort": {"_id": 1}},
    ]
    rows = list(get_collection(METRICS_COLL).aggregate(pipeline))
    lines = ["# HELP job_assistant_metrics Local MongoDB-backed metrics", "# TYPE job_assistant_metrics gauge"]
    for row in rows:
        name = str(row["_id"]).replace("-", "_").replace(".", "_")
        lines.append(f"job_assistant_{name} {float(row['total'] or 0)}")
    return Response("\n".join(lines) + "\n", media_type="text/plain")


def acknowledge_alert(alert_id: int) -> bool:
    result = get_collection(ALERTS_COLL).update_one(
        {"_id": alert_id},
        {"$set": {"status": "acknowledged", "acknowledged_at": utc_now()}},
    )
    return result.modified_count > 0
