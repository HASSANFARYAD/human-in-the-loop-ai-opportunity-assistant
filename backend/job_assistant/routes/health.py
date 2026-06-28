from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from job_assistant.auth import current_user
from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.db import db_health, list_integration_settings, list_provider_configs, storage_health
from job_assistant.runtime import runtime_status, validate_startup_configuration

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    warnings = validate_startup_configuration(strict=False)
    return {"status": "ok" if not warnings else "warning", "timestamp": datetime.utcnow().isoformat(), "warnings": warnings}


@router.get("/health/runtime")
async def health_check_runtime():
    return runtime_status()


@router.get("/health/db")
async def health_check_db():
    try:
        return db_health()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database health check failed")


@router.get("/health/storage")
async def health_check_storage():
    try:
        return storage_health()
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        raise HTTPException(status_code=503, detail="Storage health check failed")


@router.get("/health/providers")
async def health_check_providers(user: dict = Depends(current_user)):
    configured_integrations = list_integration_settings(user["id"])
    configured_providers = list_provider_configs(user["id"], include_credentials=False)
    return {
        "status": "ok",
        "configured_services": [item["service"] for item in configured_integrations],
        "integrations": configured_integrations,
        "providers": configured_providers,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/ai")
async def health_check_ai(probe: bool = False, user: dict = Depends(current_user)):
    route = ai_orchestrator.resolve_route(user["id"])
    configured = bool((route.settings.get("api_key") or "").strip())
    result: dict[str, Any] = {
        "status": "ok",
        "provider": route.provider,
        "model": route.model,
        "source": route.source,
        "configured": configured,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if probe and configured and route.provider in ("openai", "grok", "claude", "gemini", "azure_openai", "langchain_openai"):
        try:
            import requests
            headers = {"Authorization": f"Bearer {route.settings.get('api_key', '')}"}
            base = (route.settings.get("config") or {}).get("base_url", "")
            if route.provider == "gemini":
                probe_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={route.settings.get('api_key', '')}"
            elif base:
                probe_url = f"{base.rstrip('/')}/models"
            else:
                probe_url = "https://api.openai.com/v1/models"
            resp = requests.get(probe_url, headers=headers, timeout=10)
            result["probe_status"] = "reachable" if resp.ok else "unreachable"
            result["probe_http_status"] = resp.status_code
        except Exception as exc:
            result["probe_status"] = "error"
            result["probe_error"] = str(exc)[:200]
    elif probe and not configured:
        result["probe_status"] = "skipped"
        result["probe_reason"] = "No API key configured"
    elif probe:
        result["probe_status"] = "skipped"
        result["probe_reason"] = f"Provider '{route.provider}' does not support automatic probing"
    return result
