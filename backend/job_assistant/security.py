from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from job_assistant.config import settings

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        if not settings.security_headers_enabled:
            return response
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        if settings.hsts_max_age > 0:
            response.headers["Strict-Transport-Security"] = f"max-age={settings.hsts_max_age}; includeSubDomains"
        if settings.content_security_policy:
            response.headers["Content-Security-Policy"] = settings.content_security_policy
        return response


def _csrf_exempt(path: str) -> bool:
    exempt = [p.strip() for p in settings.csrf_exempt_paths.split(",") if p.strip()]
    return any(path.rstrip("/") == e.rstrip("/") or (e.endswith("*") and path.startswith(e[:-1])) for e in exempt)


def setup_csrf_protection(app: ASGIApp) -> None:
    if not settings.csrf_enabled:
        return

    @app.middleware("http")
    async def _csrf_check(request: Request, call_next: Callable) -> Response:
        if request.method in SAFE_METHODS:
            return await call_next(request)
        if _csrf_exempt(request.url.path):
            return await call_next(request)

        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        allowed = settings.cors_origin_list

        if not origin and not referer:
            logger.warning("CSRF: no Origin or Referer for %s %s", request.method, request.url.path)
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "CSRF check failed: missing origin"})

        valid = False
        if origin:
            valid = any(origin.rstrip("/") == a.rstrip("/") for a in allowed)
        if not valid and referer:
            valid = any(referer.rstrip("/").startswith(a.rstrip("/")) for a in allowed)

        if not valid:
            logger.warning("CSRF: rejected %s %s origin=%s referer=%s", request.method, request.url.path, origin, referer)
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "CSRF check failed: forbidden origin"})

        return await call_next(request)
