from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from job_assistant.auth import current_user
from job_assistant.db import (
    delete_provider_config,
    get_integration_settings,
    get_provider_config,
    list_integration_settings,
    list_provider_configs,
    save_integration_settings,
    save_provider_config,
)
from job_assistant.provider_registry import provider_registry

logger = logging.getLogger(__name__)

router = APIRouter()


class IntegrationSettingsIn(BaseModel):
    workspace_id: Optional[int] = None
    api_key: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    keep_existing_api_key_if_blank: bool = True


class ProviderConfigIn(BaseModel):
    workspace_id: Optional[int] = None
    platform: str
    provider_name: str
    auth_type: str = "api_key"
    credentials: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    is_active: bool = True
    keep_existing_credentials_if_blank: bool = True


class ProviderConfigUpdate(BaseModel):
    workspace_id: Optional[int] = None
    auth_type: str = "api_key"
    credentials: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    is_active: bool = True
    keep_existing_credentials_if_blank: bool = True


class ProviderExecuteIn(BaseModel):
    workspace_id: Optional[int] = None
    platform: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/integrations")
async def list_integrations(workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_integration_settings(user["id"], workspace_id=workspace_id)


@router.get("/integrations/{service}")
async def get_integration(service: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    settings = get_integration_settings(user["id"], service, workspace_id=workspace_id)
    return {
        "service": service,
        "has_api_key": bool((settings.get("api_key") or "").strip()),
        "config": settings.get("config", {}),
        "updated_at": settings.get("updated_at"),
    }


@router.put("/integrations/{service}")
async def upsert_integration(service: str, payload: IntegrationSettingsIn, user: dict = Depends(current_user)):
    save_integration_settings(
        user["id"],
        service,
        payload.api_key,
        payload.config,
        keep_existing_api_key_if_blank=payload.keep_existing_api_key_if_blank,
        workspace_id=payload.workspace_id,
    )
    settings = get_integration_settings(user["id"], service, workspace_id=payload.workspace_id)
    return {
        "service": service,
        "has_api_key": bool((settings.get("api_key") or "").strip()),
        "config": settings.get("config", {}),
        "updated_at": settings.get("updated_at"),
    }


@router.delete("/integrations/{service}")
async def remove_integration(service: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    delete_integration_settings(user["id"], service, workspace_id=workspace_id)
    return {"status": "success", "message": f"{service} integration removed"}


@router.get("/providers")
async def list_providers(platform: Optional[str] = None, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_provider_configs(user["id"], platform=platform, include_credentials=False, workspace_id=workspace_id)


@router.post("/providers")
async def create_provider(payload: ProviderConfigIn, user: dict = Depends(current_user)):
    try:
        save_provider_config(
            user["id"],
            payload.platform,
            payload.provider_name,
            auth_type=payload.auth_type,
            credentials=payload.credentials,
            config=payload.config,
            priority=payload.priority,
            is_active=payload.is_active,
            keep_existing_credentials_if_blank=payload.keep_existing_credentials_if_blank,
            workspace_id=payload.workspace_id,
        )
        return get_provider_config(user["id"], payload.platform, payload.provider_name, include_credentials=False, workspace_id=payload.workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/providers/{platform}/{provider_name}")
async def read_provider(platform: str, provider_name: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    provider = get_provider_config(user["id"], platform, provider_name, include_credentials=False, workspace_id=workspace_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider configuration not found")
    return provider


@router.put("/providers/{platform}/{provider_name}")
async def update_provider(platform: str, provider_name: str, payload: ProviderConfigUpdate, user: dict = Depends(current_user)):
    save_provider_config(
        user["id"],
        platform,
        provider_name,
        auth_type=payload.auth_type,
        credentials=payload.credentials,
        config=payload.config,
        priority=payload.priority,
        is_active=payload.is_active,
        keep_existing_credentials_if_blank=payload.keep_existing_credentials_if_blank,
        workspace_id=getattr(payload, "workspace_id", None),
    )
    return get_provider_config(user["id"], platform, provider_name, include_credentials=False, workspace_id=getattr(payload, "workspace_id", None))


@router.delete("/providers/{platform}/{provider_name}")
async def remove_provider(platform: str, provider_name: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    delete_provider_config(user["id"], platform, provider_name, workspace_id=workspace_id)
    return {"status": "success", "message": f"{platform}/{provider_name} provider removed"}


@router.get("/providers/health")
async def providers_health(platform: Optional[str] = None, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return {
        "status": "ok",
        "providers": provider_registry.health(user["id"], platform=platform, workspace_id=workspace_id),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/providers/execute")
async def execute_provider(payload: ProviderExecuteIn, user: dict = Depends(current_user)):
    result = provider_registry.execute_with_fallback(user["id"], payload.platform, payload.action, payload.payload, workspace_id=payload.workspace_id)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error)
    return {
        "status": "success",
        "platform": result.platform,
        "provider_name": result.provider_name,
        "result": result.result,
    }
