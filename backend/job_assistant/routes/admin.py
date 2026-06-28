from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.auth import current_user
from job_assistant.db import (
    count_ai_generations_today,
    delete_prompt_version,
    ensure_user_workspace,
    get_integration_settings,
    get_provider_config,
    list_ai_generations,
    list_provider_configs,
    list_prompt_versions,
    save_integration_settings,
    save_provider_config,
    upsert_prompt_version,
    user_has_permission,
)
from job_assistant.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_CONFIG_TYPES = {"ai_provider", "gmail", "recording_storage"}


class AdminConfigIn(BaseModel):
    workspace_id: Optional[int] = None
    type: str
    name: str = ""
    display_name: str = ""
    secret: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    notes: str = ""
    keep_existing_secret_if_blank: bool = True


class AdminConfigUpdate(BaseModel):
    workspace_id: Optional[int] = None
    name: str = ""
    display_name: str = ""
    secret: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: Optional[bool] = None
    notes: str = ""
    keep_existing_secret_if_blank: bool = True


class PromptVersionIn(BaseModel):
    name: str
    version: str
    template: str
    description: str = ""
    is_active: bool = True


class AIAskIn(BaseModel):
    workspace_id: Optional[int] = None
    system: str = "You are a helpful assistant. Return JSON only."
    prompt: str
    fallback: dict[str, Any] = Field(default_factory=dict)
    task_type: str = "general"
    prompt_version: str = ""



def _require_admin_config_access(user: dict, workspace_id: int | None = None) -> None:
    workspace = ensure_user_workspace(user["id"])
    scoped_workspace_id = int(workspace_id or workspace.get("workspace_id") or 0)
    role = str(workspace.get("role") or "owner").lower()
    if role in {"owner", "admin"}:
        return
    if scoped_workspace_id and (
        user_has_permission(user["id"], scoped_workspace_id, "integration:manage")
        or user_has_permission(user["id"], scoped_workspace_id, "provider:manage")
        or user_has_permission(user["id"], scoped_workspace_id, "workspace:manage")
    ):
        return
    raise HTTPException(status_code=403, detail="Admin configuration access is required.")


def _clean_admin_type(config_type: str) -> str:
    cleaned = (config_type or "").strip().lower()
    if cleaned not in ADMIN_CONFIG_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported admin configuration type.")
    return cleaned


def _secret_label(config_type: str) -> str:
    return "client secret" if config_type == "gmail" else "API key" if config_type == "ai_provider" else "secret"


def _active_config_value(value: Any) -> bool:
    return value is not False


def _validate_admin_config(config_type: str, name: str, config: dict[str, Any], has_secret: bool, *, partial: bool = False) -> None:
    if config_type == "ai_provider":
        if not (name or config.get("provider")):
            raise HTTPException(status_code=400, detail="Provider name is required.")
        if not str(config.get("model") or "").strip():
            raise HTTPException(status_code=400, detail="Model name is required.")
        if not has_secret and not partial:
            raise HTTPException(status_code=400, detail="AI provider API key is required.")
        timeout = config.get("timeout_seconds")
        if timeout not in (None, "") and int(timeout) <= 0:
            raise HTTPException(status_code=400, detail="Timeout seconds must be greater than zero.")
    elif config_type == "gmail":
        for key in ["client_id", "redirect_uri"]:
            if not str(config.get(key) or "").strip():
                raise HTTPException(status_code=400, detail=f"Gmail {key} is required.")
        if not has_secret and not partial:
            raise HTTPException(status_code=400, detail="Gmail client secret is required.")
        redirect_uri = str(config.get("redirect_uri") or "")
        if not redirect_uri.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Gmail redirect URI must start with http:// or https://.")
    elif config_type == "recording_storage":
        if str(config.get("storage_type") or "local").strip().lower() != "local":
            raise HTTPException(status_code=400, detail="Only local recording storage is currently supported.")
        if not str(config.get("storage_path") or "").strip():
            raise HTTPException(status_code=400, detail="Recording storage path is required.")
        max_upload_size = int(config.get("max_upload_size") or 0)
        if max_upload_size <= 0:
            raise HTTPException(status_code=400, detail="Max upload size must be greater than zero.")
        allowed = config.get("allowed_mime_types") or []
        if isinstance(allowed, str):
            allowed = [item.strip() for item in allowed.replace(",", " ").split() if item.strip()]
        if not allowed or any(not str(item).startswith("audio/") for item in allowed):
            raise HTTPException(status_code=400, detail="Allowed MIME types must include audio/* values.")


def _admin_integration_out(config_type: str, item: dict[str, Any]) -> dict[str, Any]:
    config = item.get("config") or {}
    return {
        "id": config_type,
        "type": config_type,
        "name": config.get("provider") or config.get("storage_type") or config_type,
        "display_name": config.get("display_name") or config_type.replace("_", " ").title(),
        "is_active": _active_config_value(config.get("is_active")),
        "has_secret": bool(item.get("has_api_key") or item.get("api_key")),
        "secret_label": _secret_label(config_type),
        "config": config,
        "updated_at": item.get("updated_at"),
        "source": "integration_settings",
    }


def _admin_provider_out(item: dict[str, Any]) -> dict[str, Any]:
    config = item.get("config") or {}
    return {
        "id": item.get("id") or f"ai:{item.get('provider_name')}",
        "type": "ai_provider",
        "name": item.get("provider_name") or config.get("provider") or "openai",
        "display_name": config.get("display_name") or (item.get("provider_name") or "AI Provider").replace("_", " ").title(),
        "is_active": bool(item.get("is_active")),
        "has_secret": bool(item.get("has_credentials")),
        "secret_label": "API key",
        "config": config,
        "updated_at": item.get("updated_at"),
        "source": "provider_configs",
        "priority": item.get("priority"),
    }


def _admin_configs_for_user(user_id: int, config_type: str | None = None, workspace_id: int | None = None) -> list[dict[str, Any]]:
    types = [_clean_admin_type(config_type)] if config_type else ["ai_provider", "gmail", "recording_storage"]
    out: list[dict[str, Any]] = []
    if "ai_provider" in types:
        providers = list_provider_configs(user_id, platform="ai", include_credentials=False, workspace_id=workspace_id)
        out.extend(_admin_provider_out(item) for item in providers)
        if not providers:
            legacy = get_integration_settings(user_id, "ai_provider", workspace_id=workspace_id)
            if legacy:
                out.append(_admin_integration_out("ai_provider", legacy))
    for config_type_item in [t for t in types if t in {"gmail", "recording_storage"}]:
        settings = get_integration_settings(user_id, config_type_item, workspace_id=workspace_id)
        if settings:
            out.append(_admin_integration_out(config_type_item, settings))
    return out


def _save_admin_config(user_id: int, payload: AdminConfigIn | AdminConfigUpdate, config_type: str, *, config_id: str | None = None) -> dict[str, Any]:
    name = (payload.name or "").strip().lower()
    config = dict(payload.config or {})
    if payload.display_name:
        config["display_name"] = payload.display_name.strip()
    if payload.notes:
        config["notes"] = payload.notes.strip()
    if payload.is_active is not None:
        config["is_active"] = bool(payload.is_active)
    if config_type == "ai_provider":
        provider_name = name or str(config.get("provider") or config_id or "openai").strip().lower()
        config["provider"] = str(config.get("provider") or provider_name).strip().lower()
        existing = get_provider_config(user_id, "ai", provider_name, include_credentials=False, workspace_id=payload.workspace_id)
        _validate_admin_config(config_type, provider_name, config, bool((payload.secret or "").strip() or existing.get("has_credentials")))
        if config.get("is_active") is True:
            for provider in list_provider_configs(user_id, platform="ai", include_credentials=False, workspace_id=payload.workspace_id):
                if str(provider.get("provider_name")) != provider_name and provider.get("is_active"):
                    save_provider_config(
                        user_id, "ai", str(provider.get("provider_name")),
                        auth_type=str(provider.get("auth_type") or "api_key"),
                        credentials={}, config=provider.get("config") or {},
                        priority=int(provider.get("priority") or 100), is_active=False,
                        keep_existing_credentials_if_blank=True, workspace_id=payload.workspace_id,
                    )
        save_provider_config(
            user_id, "ai", provider_name, auth_type="api_key",
            credentials={"api_key": payload.secret}, config=config,
            priority=int(config.get("priority") or 100),
            is_active=_active_config_value(config.get("is_active")),
            keep_existing_credentials_if_blank=payload.keep_existing_secret_if_blank,
            workspace_id=payload.workspace_id,
        )
        return _admin_provider_out(get_provider_config(user_id, "ai", provider_name, include_credentials=False, workspace_id=payload.workspace_id))
    existing = get_integration_settings(user_id, config_type, workspace_id=payload.workspace_id)
    _validate_admin_config(config_type, name, config, bool((payload.secret or "").strip() or (existing.get("api_key") or "").strip()))
    save_integration_settings(
        user_id, config_type, payload.secret, config,
        keep_existing_api_key_if_blank=payload.keep_existing_secret_if_blank,
        workspace_id=payload.workspace_id,
    )
    return _admin_integration_out(config_type, get_integration_settings(user_id, config_type, workspace_id=payload.workspace_id))


def _admin_config_status(user_id: int, config_type: str, workspace_id: int | None = None) -> dict[str, Any]:
    configs = _admin_configs_for_user(user_id, config_type=config_type, workspace_id=workspace_id)
    active = [item for item in configs if item.get("is_active")]
    configured = any(item.get("has_secret") or config_type == "recording_storage" for item in active)
    return {
        "type": config_type,
        "status": "configured" if configured else ("inactive" if configs else "missing"),
        "configured": configured,
        "count": len(configs),
        "active_count": len(active),
    }


@router.get("/admin/configs")
async def list_admin_configs(type: Optional[str] = None, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    _require_admin_config_access(user, workspace_id)
    return {
        "configs": _admin_configs_for_user(user["id"], config_type=type, workspace_id=workspace_id),
        "statuses": {
            config_type: _admin_config_status(user["id"], config_type, workspace_id=workspace_id)
            for config_type in ["ai_provider", "gmail", "recording_storage"]
        },
    }


@router.get("/admin/configs/{config_type}")
async def list_admin_configs_by_type(config_type: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    _require_admin_config_access(user, workspace_id)
    return {"configs": _admin_configs_for_user(user["id"], config_type=_clean_admin_type(config_type), workspace_id=workspace_id)}


@router.post("/admin/configs")
async def create_admin_config(payload: AdminConfigIn, user: dict = Depends(current_user)):
    _require_admin_config_access(user, payload.workspace_id)
    return _save_admin_config(user["id"], payload, _clean_admin_type(payload.type))


@router.put("/admin/configs/{config_type}/{config_id}")
async def update_admin_config(config_type: str, config_id: str, payload: AdminConfigUpdate, user: dict = Depends(current_user)):
    _require_admin_config_access(user, payload.workspace_id)
    return _save_admin_config(user["id"], payload, _clean_admin_type(config_type), config_id=config_id)


@router.post("/admin/configs/{config_type}/{config_id}/activate")
async def activate_admin_config(config_type: str, config_id: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    _require_admin_config_access(user, workspace_id)
    clean_type = _clean_admin_type(config_type)
    match = next((item for item in _admin_configs_for_user(user["id"], config_type=clean_type, workspace_id=workspace_id) if str(item.get("id")) == config_id or str(item.get("name")) == config_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Configuration record not found.")
    payload = AdminConfigUpdate(workspace_id=workspace_id, name=str(match.get("name") or config_id), config={**(match.get("config") or {}), "is_active": True}, is_active=True)
    return _save_admin_config(user["id"], payload, clean_type, config_id=config_id)


@router.post("/admin/configs/{config_type}/{config_id}/deactivate")
async def deactivate_admin_config(config_type: str, config_id: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    _require_admin_config_access(user, workspace_id)
    clean_type = _clean_admin_type(config_type)
    match = next((item for item in _admin_configs_for_user(user["id"], config_type=clean_type, workspace_id=workspace_id) if str(item.get("id")) == config_id or str(item.get("name")) == config_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Configuration record not found.")
    payload = AdminConfigUpdate(workspace_id=workspace_id, name=str(match.get("name") or config_id), config={**(match.get("config") or {}), "is_active": False}, is_active=False)
    return _save_admin_config(user["id"], payload, clean_type, config_id=config_id)


@router.post("/admin/configs/{config_type}/{config_id}/test")
async def test_admin_config(config_type: str, config_id: str, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    _require_admin_config_access(user, workspace_id)
    clean_type = _clean_admin_type(config_type)
    match = next((item for item in _admin_configs_for_user(user["id"], config_type=clean_type, workspace_id=workspace_id) if str(item.get("id")) == config_id or str(item.get("name")) == config_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Configuration record not found.")
    config = match.get("config") or {}
    if clean_type == "recording_storage":
        storage_path = Path(str(config.get("storage_path") or "")).expanduser().resolve()
        storage_path.mkdir(parents=True, exist_ok=True)
        probe = storage_path / ".write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    else:
        _validate_admin_config(clean_type, str(match.get("name") or config_id), config, bool(match.get("has_secret")), partial=True)
    return {"status": "success", "message": f"{clean_type} configuration is structurally valid."}


@router.get("/ai/generations")
async def ai_generations(limit: int = 100, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_ai_generations(user["id"], limit=limit, workspace_id=workspace_id)


@router.get("/ai/prompts")
async def ai_prompts(user: dict = Depends(current_user)):
    return list_prompt_versions()


@router.post("/ai/prompts")
async def save_ai_prompt(payload: PromptVersionIn, user: dict = Depends(current_user)):
    upsert_prompt_version(payload.name, payload.version, payload.template, payload.description, payload.is_active)
    return {"status": "success", "message": "Prompt version saved"}


@router.post("/ai/ask-json")
async def ask_ai_json(payload: AIAskIn, user: dict = Depends(current_user)):
    data = ai_orchestrator.ask_json(payload.system, payload.prompt, payload.fallback, user_id=user["id"], task_type=payload.task_type, prompt_version=payload.prompt_version, workspace_id=payload.workspace_id)
    return {"status": "success", "result": data}


@router.get("/ai/usage")
async def ai_usage(user: dict = Depends(current_user)):
    limit = settings.ai_daily_generation_limit
    used = count_ai_generations_today(user["id"])
    detailed = ai_usage_detailed(user["id"])
    return {
        "budget": {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used) if limit > 0 else None,
            "unlimited": limit <= 0,
        },
        **detailed,
    }


@router.get("/admin/prompts")
async def admin_list_prompts(user: dict = Depends(current_user)):
    return list_prompt_versions()


@router.post("/admin/prompts")
async def admin_upsert_prompt(payload: PromptVersionIn, user: dict = Depends(current_user)):
    upsert_prompt_version(payload.name, payload.version, payload.template, description=payload.description, is_active=payload.is_active)
    return {"status": "success"}


@router.delete("/admin/prompts")
async def admin_delete_prompt(name: str, version: str, user: dict = Depends(current_user)):
    ok = delete_prompt_version(name, version)
    if not ok:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return {"status": "ok"}
