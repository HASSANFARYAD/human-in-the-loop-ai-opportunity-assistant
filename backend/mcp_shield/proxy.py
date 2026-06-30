import json
import time
from collections.abc import AsyncGenerator
from typing import Any, Optional

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from mcp_shield.config import settings
from mcp_shield.database import get_db, write_alert, write_event
from mcp_shield.events import ShieldAlert, ShieldEvent
from mcp_shield.rules import check_rules
from mcp_shield.security import scan_for_injection


def _extract_session_id(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.headers.get("x-session-id", None)


def _detect_llm_provider(path: str, body: dict[str, Any]) -> Optional[str]:
    provider_map = {
        "openai": "openai",
        "claude": "claude",
        "anthropic": "claude",
        "gemini": "gemini",
        "grok": "grok",
        "groq": "groq",
    }
    text = json.dumps(body).lower() if body else path.lower()
    for keyword, provider in provider_map.items():
        if keyword in text:
            return provider
    return None


def _sanitize_body(body: Any) -> Any:
    if not isinstance(body, (dict, list)):
        return {"__type__": type(body).__name__}

    sensitive_keys = {"password", "token", "secret", "authorization", "api_key", "jwt"}

    if isinstance(body, list):
        return [_sanitize_body(item) if isinstance(item, (dict, list)) else item for item in body]

    sanitized: dict[str, Any] = {}
    for key, value in body.items():
        lower_key = key.lower()
        if lower_key in sensitive_keys:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, (dict, list)):
            sanitized[key] = _sanitize_body(value)
        elif isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:100] + "..."
        else:
            sanitized[key] = value
    return sanitized


def _build_target_url(request: Request) -> str:
    target_url = f"{settings.target_base_url}{request.url.path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    return target_url


def _build_forward_headers(request: Request) -> dict[str, str]:
    excluded = {
        "host", "content-length", "content-encoding", "transfer-encoding",
        "connection",
    }
    return {
        k: v for k, v in request.headers.items() if k.lower() not in excluded
    }


def _is_sse_request(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/event-stream" in accept


async def _forward_request(
    request: Request, body_bytes: bytes
) -> Response:
    target_url = _build_target_url(request)
    headers = _build_forward_headers(request)

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds
        ) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body_bytes,
                follow_redirects=True,
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )
    except httpx.ConnectError:
        return Response(
            content=json.dumps({
                "error": "Backend unavailable",
                "detail": f"Could not connect to {settings.target_base_url}",
            }),
            status_code=502,
            media_type="application/json",
        )


async def _forward_streaming(request: Request, body_bytes: bytes) -> StreamingResponse:
    target_url = _build_target_url(request)
    headers = _build_forward_headers(request)

    async def stream_generator() -> AsyncGenerator[bytes, None]:
        try:
            async with httpx.AsyncClient(
                timeout=settings.stream_timeout_seconds
            ) as client:
                async with client.stream(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body_bytes,
                    follow_redirects=True,
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except httpx.ConnectError:
            yield json.dumps({
                "event": "error",
                "data": json.dumps({
                    "error": "Backend unavailable",
                    "detail": f"Could not connect to {settings.target_base_url}",
                }),
            }).encode() + b"\n\n"

    return StreamingResponse(
        content=stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def handle_proxy_request(request: Request) -> Response:
    body_bytes = await request.body()

    content_type = request.headers.get("content-type", "").lower()
    body: Any = {}
    if body_bytes:
        if "application/json" in content_type or content_type.endswith("/json"):
            try:
                body = json.loads(body_bytes)
            except (json.JSONDecodeError, ValueError):
                body = {}
        else:
            body = {}

    session_id = _extract_session_id(request)
    llm_provider = _detect_llm_provider(request.url.path, body if isinstance(body, dict) else {})
    sanitized = _sanitize_body(body) if isinstance(body, dict) else {"__non_json__": True}

    body_for_scan = body if isinstance(body, dict) else {}
    injection_result = scan_for_injection(body_for_scan, request.url.path)
    domain_result = await check_rules(body_for_scan, session_id, request.url.path)

    combined_risk = max(injection_result.risk_score, domain_result.risk_score)
    threat_type = injection_result.threat_type or domain_result.threat_type

    if combined_risk >= 61:
        event = ShieldEvent(
            session_id=session_id,
            request_method=request.method,
            request_path=request.url.path,
            body_snapshot=json.dumps(sanitized, default=str)[:2000],
            threat_type=threat_type,
            risk_score=combined_risk,
            action_taken="BLOCK",
        )
        async with get_db() as db:
            await write_event(db, event.model_dump())
            if domain_result.detail:
                await write_alert(
                    db,
                    ShieldAlert(
                        event_id=event.event_id,
                        alert_type="domain_rule",
                        severity="HIGH",
                        detail=domain_result.detail,
                    ).model_dump(),
                )
        return Response(
            content=json.dumps({
                "error": "Request blocked by MCP Shield",
                "threat_type": threat_type,
                "risk_score": combined_risk,
                "detail": domain_result.detail or injection_result.detail,
            }),
            status_code=403,
            media_type="application/json",
        )

    start = time.monotonic()

    is_sse = _is_sse_request(request)
    response = await (
        _forward_streaming(request, body_bytes) if is_sse
        else _forward_request(request, body_bytes)
    )

    latency = int((time.monotonic() - start) * 1000)

    event = ShieldEvent(
        session_id=session_id,
        request_method=request.method,
        request_path=request.url.path,
        response_status=response.status_code,
        latency_ms=latency,
        llm_provider=llm_provider,
        body_snapshot=json.dumps(sanitized, default=str)[:2000],
        threat_type=threat_type,
        risk_score=combined_risk,
        action_taken="ALLOW",
    )

    async with get_db() as db:
        await write_event(db, event.model_dump())

    return response
