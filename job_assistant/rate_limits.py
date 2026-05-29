from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from job_assistant.config import settings
from job_assistant.db import increment_usage_counter


@lru_cache(maxsize=1)
def _redis_client() -> Any:
    if not settings.redis_url:
        return None
    try:
        import redis

        return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
    except Exception:
        return None


def _window(minutes: int = 1, hours: int = 0) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    if hours:
        start = now.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=hours)
    else:
        start = now.replace(second=0, microsecond=0)
        end = start + timedelta(minutes=minutes)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _limit_for_path(path: str) -> tuple[str, int, int]:
    if path.startswith("/api/v1/ai/"):
        return "ai_generation", settings.rate_limit_ai_per_hour, 60
    if path.startswith("/api/v1/feedback"):
        return "feedback", settings.rate_limit_feedback_per_hour, 60
    if path.startswith("/api/v1/posts"):
        return "publishing", settings.rate_limit_publish_per_hour, 60
    return "api_request", settings.rate_limit_per_minute, 1


def _redis_increment(resource_type: str, window_start: str, window_end: str, ip_address: str, window_minutes: int) -> int | None:
    if settings.rate_limit_backend.lower() not in {"redis", "gateway"}:
        return None
    client = _redis_client()
    if client is None:
        return None
    key = f"rate:{resource_type}:{ip_address}:{window_start}"
    try:
        count = int(client.incr(key))
        if count == 1:
            ttl = max(60, window_minutes * 60)
            client.expire(key, ttl)
        return count
    except Exception:
        return None


async def sqlite_rate_limit_middleware(request: Request, call_next):
    if not settings.rate_limits_enabled or not request.url.path.startswith("/api/"):
        return await call_next(request)
    if request.method.upper() == "OPTIONS":
        return await call_next(request)

    resource_type, limit, window_minutes = _limit_for_path(request.url.path)
    if limit <= 0:
        return await call_next(request)

    if window_minutes >= 60:
        window_start, window_end = _window(hours=window_minutes // 60)
    else:
        window_start, window_end = _window(minutes=window_minutes)

    ip_address = _client_ip(request)
    count = _redis_increment(resource_type, window_start, window_end, ip_address, window_minutes)
    backend = "redis" if count is not None and settings.rate_limit_backend.lower() in {"redis", "gateway"} else "sqlite"
    if count is None:
        count = increment_usage_counter(
            resource_type=resource_type,
            window_start=window_start,
            window_end=window_end,
            ip_address=ip_address,
        )
    if count > limit:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded. Please wait and try again.",
                "resource_type": resource_type,
                "limit": limit,
                "window_end": window_end,
            },
            headers={"Retry-After": "60"},
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
    response.headers["X-RateLimit-Resource"] = resource_type
    response.headers["X-RateLimit-Backend"] = backend
    return response
