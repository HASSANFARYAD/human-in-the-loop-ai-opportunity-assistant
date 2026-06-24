from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Cookie, Depends, File, Form, HTTPException, Request, UploadFile, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from starlette.responses import FileResponse, RedirectResponse

from job_assistant.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    current_user,
    public_user,
    register_user,
    request_password_reset,
    reset_password,
    revoke_refresh_token,
    user_from_refresh_token,
)
from job_assistant.compliance import admin_review, apply_retention_policies, approve_user_deletion, export_user_data, list_compliance_exports, request_user_deletion
from job_assistant.config import settings
from job_assistant.db import (
    create_conversation,
    list_conversations,
    get_conversation,
    update_conversation,
    delete_conversation,
    add_conversation_message,
    get_conversation_messages,
    create_feedback,
    create_reminder,
    cleanup_non_opportunity_records,
    count_ai_generations_today,
    record_score_feedback,
    db_health,
    delete_job,
    delete_user_data,
    due_reminders,
    get_evaluation,
    get_job,
    get_materials,
    get_profile,
    get_feedback,
    get_integration_settings,
    insert_job,
    list_audit_logs,
    create_automation_rule,
    delete_automation_rule,
    list_ai_generations,
    list_automation_errors,
    list_automation_rules,
    list_automation_runs,
    list_prompt_versions,
    update_automation_rule,
    upsert_prompt_version,
    list_feedback,
    list_integration_settings,
    list_jobs,
    list_gmail_messages,
    list_interview_prep,
    list_recordings,
    list_resume_reviews,
    save_evaluation,
    save_integration_settings,
    save_materials,
    save_gmail_messages,
    save_interview_prep,
    save_recording,
    save_resume_review,
    delete_integration_settings,
    delete_provider_config,
    get_provider_config,
    list_provider_configs,
    save_provider_config,
    storage_health,
    update_feedback_status,
    usage_summary,
    add_workspace_member,
    create_organization,
    create_workspace,
    create_post,
    enterprise_summary,
    ensure_user_workspace,
    list_permissions,
    list_posts,
    list_role_permissions,
    list_roles,
    list_shared_resources,
    list_user_workspaces,
    list_workspace_members,
    share_resource,
    user_has_permission,
    update_status,
    upsert_profile,
    create_profile,
    list_profiles,
    update_profile_fields,
    set_default_profile,
    delete_profile,
)
from job_assistant.runtime import runtime_status, validate_startup_configuration
from job_assistant.provider_registry import provider_registry
from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.agent_chat import chat_reply, chat_reply_stream, classify_intent, run_job_search
from job_assistant.automation_engine import automation_engine
from job_assistant.observability import acknowledge_alert, metrics_summary, prometheus_text
from job_assistant.publishing_engine import approve_post, publish_post, validate_target
from job_assistant.services.apify_integration import apify_items_to_opportunities, build_run_input, run_actor_for_items
from job_assistant.services.generation import generate_materials
from job_assistant.services.gmail_ingest import build_gmail_authorization_url, disconnect_gmail, exchange_gmail_code, get_gmail_connection
from job_assistant.services.job_import import import_opportunities
from job_assistant.services.job_context import build_job_context, choose_primary_focus_area, extract_profile_skills
from job_assistant.services.opportunity_classifier import (
    VALID_OPPORTUNITY_CATEGORIES,
    annotate_opportunity,
    extract_opportunities_from_container,
    is_job_like,
    scoring_gate,
)
from job_assistant.services.job_source_scrapers import ScraperError, UnsupportedSourceUrl, indeed_url_with_work_location_intent, get_scraper_for_url, is_job_listing_url
from job_assistant.services.parsing import extract_job_from_text, extract_profile_from_resume, extract_text_from_upload, jobs_from_csv
from job_assistant.services.resume_builder import RESUME_TEMPLATES, RESUME_STRUCTURE_KEYS, is_valid_template, render_resume_docx
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.rapidapi_linkedin import search_linkedin_jobs, rapidapi_items_to_opportunities
from job_assistant.services.scoring import score_job
from job_assistant.worker_queue import enqueue_job, list_worker_jobs, worker_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _frontend_redirect(path: str, params: dict[str, str]) -> str:
    base_url = settings.frontend_base_url.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("Invalid FRONTEND_BASE_URL configured for OAuth redirect: %s", settings.frontend_base_url)
        base_url = "http://localhost:3000"
    safe_path = path if path.startswith("/") and not path.startswith("//") else "/"
    return f"{base_url}{safe_path}?{urlencode(params)}"


class ProfileCreate(BaseModel):
    name: str = ""
    cv_text: str = ""
    target_roles: str = ""
    industries: str = ""
    locations: str = ""
    remote_preference: str = ""
    salary_expectations: str = ""
    work_authorization: str = ""
    years_experience: str = ""
    skills: str = ""
    deal_breakers: str = ""
    full_name: str = ""
    email: str = ""
    preferred_role: str = ""
    country: str = ""
    job_preferences: str = ""
    platforms: str = ""
    resume_name: str = ""
    integration_status: str = ""


class JobCreate(BaseModel):
    workspace_id: Optional[int] = None
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    remote_type: Optional[str] = None
    url: Optional[str] = None
    source: str
    description: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    deadline: Optional[str] = None
    opportunity_type: str = "job"
    classification: Optional[str] = None
    classification_reason: Optional[str] = None
    classification_confidence: Optional[float] = None
    opportunity_confidence: Optional[float] = None
    importable: Optional[bool] = None
    blocked_reason: Optional[str] = None


WORK_LOCATION_FILTERS = {"all", "remote", "hybrid", "onsite"}
REMOTE_LOCATION_INDICATORS = ("remote", "work from home", "wfh", "anywhere")
HYBRID_LOCATION_INDICATORS = ("hybrid", "partially remote")
ONSITE_LOCATION_INDICATORS = ("onsite", "on-site", "on site", "office")


def _normalize_work_location_filter(value: Any) -> str:
    normalized = str(value or "all").strip().lower()
    if not normalized:
        normalized = "all"
    if normalized not in WORK_LOCATION_FILTERS:
        raise ValueError("work_location_filter must be one of: all, remote, hybrid, onsite")
    return normalized


def _opportunity_location_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key, ""))
        for key in ["title", "company", "location", "remote_type", "description", "raw_text"]
    ).lower()


def _matches_work_location_filter(item: dict[str, Any], work_location_filter: str) -> bool:
    if work_location_filter == "all":
        return True
    haystack = _opportunity_location_text(item)
    has_remote = any(indicator in haystack for indicator in REMOTE_LOCATION_INDICATORS)
    has_hybrid = any(indicator in haystack for indicator in HYBRID_LOCATION_INDICATORS)
    has_onsite = any(indicator in haystack for indicator in ONSITE_LOCATION_INDICATORS)
    if work_location_filter == "remote":
        return has_remote and not has_hybrid
    if work_location_filter == "hybrid":
        return has_hybrid
    if work_location_filter == "onsite":
        return not has_remote and not has_hybrid and (has_onsite or bool(str(item.get("location") or "").strip()))
    return True


def _filter_by_work_location(items: list[dict[str, Any]], work_location_filter: str) -> tuple[list[dict[str, Any]], int]:
    filtered = [item for item in items if _matches_work_location_filter(item, work_location_filter)]
    return filtered, len(items) - len(filtered)


def _url_error_detail(status: str, message: str, source: str = "") -> dict[str, str]:
    detail = {"status": status, "message": message}
    if source:
        detail["source"] = source
    return detail


def _scraper_error_response(exc: ScraperError, source: str = "") -> HTTPException:
    error_text = str(exc)
    source_name = source.lower() if source else ""
    if "indeed" in error_text.lower():
        source_name = "indeed"
    if "status 403" in error_text.lower() or "blocked" in error_text.lower():
        return HTTPException(
            status_code=400,
            detail=_url_error_detail(
                "blocked",
                "Indeed blocked the page fetch. Try using another supported URL, a supported extractor, or paste the job details manually.",
                source_name or "indeed",
            ),
        )
    return HTTPException(
        status_code=400,
        detail=_url_error_detail(
            "url_error",
            "The URL could not be fetched. Please check the link and try again.",
            source_name,
        ),
    )


class DiscoveryExtractIn(BaseModel):
    workspace_id: Optional[int] = None
    raw: str
    source: str = "Manual"
    opportunity_type: str = "auto"
    work_location_filter: str = "all"

    @validator("work_location_filter", pre=True, always=True)
    def validate_work_location_filter(cls, value: Any) -> str:
        return _normalize_work_location_filter(value)


class DiscoveryPublicIn(BaseModel):
    query: str = ""
    sources: list[str] = Field(default_factory=list)
    limit_per_source: int = 20
    opportunity_type: str = "auto"
    remote_type: str = "all"
    location: str = ""
    keywords: str = ""
    country: str = ""


class DiscoveryFromProfileIn(BaseModel):
    sources: list[str] = Field(default_factory=list)
    limit_per_source: int = 10
    save_results: bool = False
    score_results: bool = True


class DiscoveryImportIn(BaseModel):
    workspace_id: Optional[int] = None
    opportunities: list[Dict[str, Any]] = Field(default_factory=list)


class DiscoveryImportUrlIn(BaseModel):
    workspace_id: Optional[int] = None
    url: str
    source: str = "Manual"
    page_limit: int = 2
    work_location_filter: str = "all"

    @validator("work_location_filter", pre=True, always=True)
    def validate_work_location_filter(cls, value: Any) -> str:
        return _normalize_work_location_filter(value)


class DiscoveryRapidApiIn(BaseModel):
    workspace_id: Optional[int] = None
    title_filter: str
    location_filter: str = "United States OR United Kingdom"
    offset: int = 0


class DiscoveryApifyIn(BaseModel):
    workspace_id: Optional[int] = None
    url: str


class ReminderCreate(BaseModel):
    job_id: int
    kind: str
    remind_at: str
    note: Optional[str] = None


class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str = ""


class UserLogin(BaseModel):
    email: str
    password: str


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    password: str


class IntegrationSettingsIn(BaseModel):
    workspace_id: Optional[int] = None
    api_key: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)
    keep_existing_api_key_if_blank: bool = True


class IntegrationSettingsOut(BaseModel):
    service: str
    has_api_key: bool
    config: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[str] = None


class ProviderConfigIn(BaseModel):
    workspace_id: Optional[int] = None
    platform: str
    provider_name: str
    auth_type: str = "api_key"
    credentials: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    is_active: bool = True
    keep_existing_credentials_if_blank: bool = True


class ProviderConfigUpdate(BaseModel):
    workspace_id: Optional[int] = None
    auth_type: str = "api_key"
    credentials: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    is_active: bool = True
    keep_existing_credentials_if_blank: bool = True


class ProviderExecuteIn(BaseModel):
    workspace_id: Optional[int] = None
    platform: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class AdminConfigIn(BaseModel):
    workspace_id: Optional[int] = None
    type: str
    name: str = ""
    display_name: str = ""
    secret: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    notes: str = ""
    keep_existing_secret_if_blank: bool = True


class AdminConfigUpdate(BaseModel):
    workspace_id: Optional[int] = None
    name: str = ""
    display_name: str = ""
    secret: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: Optional[bool] = None
    notes: str = ""
    keep_existing_secret_if_blank: bool = True


class AIAskIn(BaseModel):
    workspace_id: Optional[int] = None
    system: str = "You are a helpful assistant. Return JSON only."
    prompt: str
    fallback: Dict[str, Any] = Field(default_factory=dict)
    task_type: str = "general"
    prompt_version: str = ""


class AgentChatIn(BaseModel):
    message: str
    history: list[Dict[str, str]] = Field(default_factory=list)
    conversation_id: Optional[int] = None
    workspace_id: Optional[int] = None


class ConversationCreateIn(BaseModel):
    title: str = ""
    workspace_id: Optional[int] = None


class ConversationUpdateIn(BaseModel):
    title: str


class ScoreFeedbackIn(BaseModel):
    signal: str  # "relevant" | "irrelevant"
    workspace_id: Optional[int] = None


class PromptVersionIn(BaseModel):
    name: str
    version: str
    template: str
    description: str = ""
    is_active: bool = True


class AutomationRuleIn(BaseModel):
    workspace_id: Optional[int] = None
    name: str
    trigger_event: str = "manual"
    action_type: str = "notify"
    conditions: Dict[str, Any] = Field(default_factory=dict)
    action_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    human_approval_required: bool = True


class AutomationRuleUpdate(BaseModel):
    workspace_id: Optional[int] = None
    name: Optional[str] = None
    trigger_event: Optional[str] = None
    action_type: Optional[str] = None
    conditions: Dict[str, Any] = Field(default_factory=dict)
    action_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: Optional[bool] = None
    human_approval_required: Optional[bool] = None


class AutomationTriggerIn(BaseModel):
    workspace_id: Optional[int] = None
    trigger_event: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class FeedbackCreate(BaseModel):
    workspace_id: Optional[int] = None
    category: str = "General Suggestion"
    title: str
    description: str
    severity: str = "medium"
    attachment_url: str = ""
    page_url: str = ""
    user_agent: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FeedbackStatusUpdate(BaseModel):
    status: str


class PostCreate(BaseModel):
    workspace_id: Optional[int] = None
    title: str = ""
    base_content: str
    status: str = "draft"
    scheduled_at: Optional[str] = None
    targets: list[Dict[str, Any]] = Field(default_factory=list)


class OrganizationCreate(BaseModel):
    name: str


class WorkspaceCreate(BaseModel):
    organization_id: int
    name: str
    description: str = ""


class WorkspaceMemberIn(BaseModel):
    email: str
    role: str = "viewer"


class SharedResourceIn(BaseModel):
    workspace_id: int
    resource_type: str
    resource_id: str
    access_level: str = "read"
    expires_at: str = ""


class PublishRequest(BaseModel):
    dry_run: Optional[bool] = None


class WorkerJobIn(BaseModel):
    queue_name: str = "default"
    job_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    run_after: str = ""


class DeletionRequestIn(BaseModel):
    reason: str = ""


class DeletionApproveIn(BaseModel):
    target_user_id: int


class BatchScoreIn(BaseModel):
    job_ids: list[int] = Field(default_factory=list)
    score_all_unscored: bool = False
    profile_id: Optional[int] = None


class ResumeReviewIn(BaseModel):
    job_id: Optional[int] = None
    resume_text: str = ""
    target_role: str = ""


class RecordingIn(BaseModel):
    job_id: Optional[int] = None
    title: str = "Interview practice recording"
    mime_type: str = "audio/webm"
    data_url: str
    duration_ms: int = 0


class GmailMessagesIn(BaseModel):
    messages: list[Dict[str, Any]] = Field(default_factory=list)


def _recording_storage_config(user_id: int) -> dict[str, Any]:
    settings = get_integration_settings(user_id, "recording_storage")
    config = settings.get("config") or {}
    if settings and config.get("is_active") is False:
        raise HTTPException(status_code=400, detail="Recording storage configuration is inactive.")
    storage_type = str(config.get("storage_type") or "local").strip().lower()
    if storage_type != "local":
        raise HTTPException(status_code=400, detail=f"Recording storage type '{storage_type}' is not supported by this deployment.")
    storage_path = str(config.get("storage_path") or "data/recordings").strip()
    allowed = config.get("allowed_mime_types") or ["audio/webm", "audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg"]
    if isinstance(allowed, str):
        allowed = [item.strip() for item in allowed.replace(",", " ").split() if item.strip()]
    return {
        "storage_type": storage_type,
        "storage_path": storage_path,
        "max_upload_size": int(config.get("max_upload_size") or 25 * 1024 * 1024),
        "allowed_mime_types": allowed,
    }


def _safe_audio_extension(filename: str, mime_type: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4"}:
        return suffix
    return {
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }.get(mime_type, ".webm")


ADMIN_CONFIG_TYPES = {"ai_provider", "gmail", "recording_storage"}


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


def _require_workspace_admin(user: dict, workspace_id: int | None = None) -> None:
    workspace = ensure_user_workspace(user["id"])
    scoped_workspace_id = int(workspace_id or workspace.get("workspace_id") or 0)
    role = str(workspace.get("role") or "owner").lower()
    if role in {"owner", "admin"}:
        return
    if scoped_workspace_id and user_has_permission(user["id"], scoped_workspace_id, "workspace:manage"):
        return
    raise HTTPException(status_code=403, detail="Workspace administrator access is required.")


def _auth_payload(user: dict, response: Response) -> dict[str, Any]:
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user, days=settings.refresh_token_expire_days)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=refresh_token,
        max_age=settings.session_cookie_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )
    return {"access_token": access_token, "token_type": "bearer", "user": public_user(user)}


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
                        user_id,
                        "ai",
                        str(provider.get("provider_name")),
                        auth_type=str(provider.get("auth_type") or "api_key"),
                        credentials={},
                        config=provider.get("config") or {},
                        priority=int(provider.get("priority") or 100),
                        is_active=False,
                        keep_existing_credentials_if_blank=True,
                        workspace_id=payload.workspace_id,
                    )
        save_provider_config(
            user_id,
            "ai",
            provider_name,
            auth_type="api_key",
            credentials={"api_key": payload.secret},
            config=config,
            priority=int(config.get("priority") or 100),
            is_active=_active_config_value(config.get("is_active")),
            keep_existing_credentials_if_blank=payload.keep_existing_secret_if_blank,
            workspace_id=payload.workspace_id,
        )
        return _admin_provider_out(get_provider_config(user_id, "ai", provider_name, include_credentials=False, workspace_id=payload.workspace_id))

    existing = get_integration_settings(user_id, config_type, workspace_id=payload.workspace_id)
    _validate_admin_config(config_type, name, config, bool((payload.secret or "").strip() or (existing.get("api_key") or "").strip()))
    save_integration_settings(
        user_id,
        config_type,
        payload.secret,
        config,
        keep_existing_api_key_if_blank=payload.keep_existing_secret_if_blank,
        workspace_id=payload.workspace_id,
    )
    return _admin_integration_out(config_type, get_integration_settings(user_id, config_type, workspace_id=payload.workspace_id))



# Milestone 7: organization, workspace, RBAC, sharing, and admin foundations
@router.get("/enterprise/bootstrap")
@router.post("/enterprise/bootstrap")
async def enterprise_bootstrap(user: dict = Depends(current_user)):
    return {"workspace": ensure_user_workspace(user["id"]), "summary": enterprise_summary(user["id"])}


@router.get("/enterprise/summary")
async def get_enterprise_summary(user: dict = Depends(current_user)):
    return enterprise_summary(user["id"])


@router.get("/workspaces")
async def get_workspaces(user: dict = Depends(current_user)):
    return list_user_workspaces(user["id"])


@router.post("/organizations")
async def post_organization(payload: OrganizationCreate, user: dict = Depends(current_user)):
    try:
        return create_organization(user["id"], payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/workspaces")
async def post_workspace(payload: WorkspaceCreate, user: dict = Depends(current_user)):
    try:
        return create_workspace(user["id"], payload.organization_id, payload.name, payload.description)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/workspaces/{workspace_id}/members")
async def get_workspace_members(workspace_id: int, user: dict = Depends(current_user)):
    try:
        return list_workspace_members(user["id"], workspace_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/workspaces/{workspace_id}/members")
async def post_workspace_member(workspace_id: int, payload: WorkspaceMemberIn, user: dict = Depends(current_user)):
    try:
        return add_workspace_member(user["id"], workspace_id, payload.email, payload.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/roles")
async def get_roles():
    return list_roles()


@router.get("/permissions")
async def get_permissions(role: Optional[str] = None):
    if role:
        return list_role_permissions(role)
    return {"permissions": list_permissions(), "role_permissions": list_role_permissions()}


@router.get("/permissions/check")
async def check_permission(workspace_id: int, permission: str, user: dict = Depends(current_user)):
    return {"workspace_id": workspace_id, "permission": permission, "allowed": user_has_permission(user["id"], workspace_id, permission)}


@router.get("/shared-resources")
async def get_shared_resources(workspace_id: Optional[int] = None, limit: int = 100, user: dict = Depends(current_user)):
    try:
        return list_shared_resources(user["id"], workspace_id=workspace_id, limit=limit)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/shared-resources")
async def post_shared_resource(payload: SharedResourceIn, user: dict = Depends(current_user)):
    try:
        share_id = share_resource(user["id"], payload.workspace_id, payload.resource_type, payload.resource_id, payload.access_level, payload.expires_at)
        return {"id": share_id, "status": "success"}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@router.get("/usage")
async def get_usage(user: dict = Depends(current_user)):
    return {"status": "ok", "usage": usage_summary(user["id"])}


@router.get("/observability")
async def get_observability(hours: int = 24, user: dict = Depends(current_user)):
    return metrics_summary(hours=hours)


@router.get("/metrics")
async def get_prometheus_metrics():
    return prometheus_text()


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return {"status": "success" if acknowledge_alert(alert_id) else "not_found"}


@router.get("/workers/health")
async def get_worker_health(user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return worker_health()


@router.get("/workers/jobs")
async def get_worker_jobs(limit: int = 100, status: str = "", user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return list_worker_jobs(limit=limit, status=status)


@router.post("/workers/jobs")
async def post_worker_job(payload: WorkerJobIn, user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    job_id = enqueue_job(payload.job_type, payload.payload, queue_name=payload.queue_name, run_after=payload.run_after)
    return {"id": job_id, "status": "queued"}


@router.post("/auth/register")
async def register(user_data: UserRegister, response: Response):
    try:
        user = register_user(user_data.email, user_data.password, user_data.full_name)
        return _auth_payload(user, response)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail="Failed to register user")


@router.post("/auth/login")
async def login(login_data: UserLogin, response: Response):
    user = authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_payload(user, response)


@router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, request: Request):
    try:
        ip_address = ""
        user_agent = ""
        if request is not None:
            ip_address = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip() or (request.client.host if request.client else "")
            user_agent = request.headers.get("user-agent", "")
        request_password_reset(payload.email, settings.frontend_reset_password_url, ip_address=ip_address, user_agent=user_agent)
    except Exception as e:
        logger.error("Password reset request failed: %s", e)
        if settings.is_production:
            raise HTTPException(status_code=500, detail="Unable to process password reset request")
    return {"status": "success", "message": "If an account exists for that email, a password reset link has been sent."}


@router.post("/auth/reset-password")
async def reset_password_confirm(payload: ResetPasswordIn):
    try:
        if reset_password(payload.token, payload.password):
            return {"status": "success", "message": "Password has been reset."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    raise HTTPException(status_code=400, detail="Invalid or expired password reset token.")


@router.post("/auth/refresh")
async def refresh_auth(
    response: Response,
    refresh_token: str = Cookie(default="", alias=settings.session_cookie_name),
):
    user = user_from_refresh_token(refresh_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    revoke_refresh_token(refresh_token)
    return _auth_payload(user, response)


@router.post("/auth/logout")
async def logout(
    response: Response,
    refresh_token: str = Cookie(default="", alias=settings.session_cookie_name),
):
    if refresh_token:
        revoke_refresh_token(refresh_token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
    return {"status": "success"}


@router.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)




@router.get("/integrations")
async def list_integrations(workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    """List the signed-in user's configured integrations without exposing secrets."""
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
    """List configured provider-abstraction records without exposing credentials."""
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
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used) if limit > 0 else None,
        "unlimited": limit <= 0,
    }


@router.post("/jobs/{job_id}/score-feedback")
async def post_score_feedback(job_id: int, payload: ScoreFeedbackIn, user: dict = Depends(current_user)):
    job = get_job(job_id, user["id"], workspace_id=payload.workspace_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        record_score_feedback(user["id"], job_id, payload.signal, workspace_id=payload.workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "signal": payload.signal.strip().lower()}


def _resolve_job_for_reference(user_id: int, reference: str, workspace_id: Optional[int] = None) -> Optional[dict[str, Any]]:
    """Find the job a chat message refers to: by name match, else most recent."""
    jobs = list_jobs(user_id, workspace_id=workspace_id)
    if not jobs:
        return None
    ref = (reference or "").strip().lower()
    if ref:
        for job in jobs:
            haystack = f"{job.get('title', '')} {job.get('company', '')}".lower()
            if ref in haystack:
                return job
    return jobs[0]  # list_jobs returns newest first


def _run_agent_intent(intent: str, routing: dict[str, Any], profile: dict[str, Any], user_id: int, workspace_id: Optional[int], *, message: str = "", history: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
    """Execute a single agent intent and return its result section."""
    if intent == "job_search":
        listings = run_job_search(profile, routing["search_query"], user_id=user_id)
        return {"agent": "job_search", "type": "listings", "data": listings,
                "message": f"Found {len(listings)} matching opportunity/opportunities." if listings
                else "No matching listings found right now. Try refining your roles or skills."}

    if intent in ("tailor_resume", "interview_prep"):
        job = _resolve_job_for_reference(user_id, routing["job_reference"], workspace_id)
        if not job:
            return {"agent": intent, "type": "error",
                    "message": "I couldn't find a saved opportunity to work from. Import or open a job first."}

        if intent == "tailor_resume":
            if not _profile_has_resume_context(profile):
                return {"agent": intent, "type": "error",
                        "message": "Add your resume or profile details before I can tailor a resume."}
            tailored = _llm_tailored_resume(profile, job, user_id)
            saved = save_resume_review(user_id, tailored, int(job["id"]))
            return {"agent": intent, "type": "tailored_resume", "job": {"id": job["id"], "title": job.get("title"), "company": job.get("company")}, "data": saved}

        evaluation = get_evaluation(int(job["id"]), user_id) or {}
        if not evaluation:
            try:
                evaluation = score_job(profile, job, user_id=user_id)
            except Exception:
                evaluation = {}
        prep = _llm_interview_prep(profile, job, evaluation, user_id)
        saved = save_interview_prep(user_id, int(job["id"]), prep)
        return {"agent": intent, "type": "interview_prep", "job": {"id": job["id"], "title": job.get("title"), "company": job.get("company")}, "data": saved}

    # chat / fallback — a genuine, grounded conversational reply
    opportunities = list_jobs(user_id, workspace_id=workspace_id)
    reply = chat_reply(message, history=history, profile=profile, opportunities=opportunities, user_id=user_id)
    return {"agent": "chat", "type": "message", "message": reply}


@router.post("/agent/chat")
async def agent_chat(payload: AgentChatIn, user: dict = Depends(current_user)):
    user_id = user["id"]
    routing = classify_intent(payload.message, history=payload.history, user_id=user_id)
    profile = get_profile(user_id) or {}
    sections = [_run_agent_intent(intent, routing, profile, user_id, payload.workspace_id, message=payload.message, history=payload.history) for intent in routing["intents"]]
    return {"intents": routing["intents"], "sections": sections}


@router.post("/agent/chat/stream")
async def agent_chat_stream(payload: AgentChatIn, user: dict = Depends(current_user)):
    user_id = user["id"]
    workspace_id = payload.workspace_id
    history = payload.history
    message = payload.message
    conversation_id = payload.conversation_id

    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    def event_stream():
        nonlocal conversation_id
        try:
            # Auto-create conversation on first message
            if not conversation_id:
                title = (message[:80] + "...") if len(message) > 80 else message
                conversation_id = create_conversation(user_id, title, workspace_id=workspace_id)
                yield _sse("conversation", {"conversation_id": conversation_id})

            # Save user message
            add_conversation_message(conversation_id, "user", message)

            routing = classify_intent(message, history=history, user_id=user_id)
            profile = get_profile(user_id) or {}
            yield _sse("intents", {"intents": routing["intents"]})

            assistant_sections: list[dict[str, Any]] = []
            for intent in routing["intents"]:
                try:
                    if intent == "chat":
                        opportunities = list_jobs(user_id, workspace_id=workspace_id)
                        yield _sse("section", {"agent": "chat", "type": "message", "message": ""})
                        full_reply = ""
                        stream_iter = chat_reply_stream(
                            message, history=history, profile=profile,
                            opportunities=opportunities, user_id=user_id,
                        )
                        for token in stream_iter:
                            full_reply += token
                            yield _sse("delta", {"text": token})
                        assistant_sections.append({"agent": "chat", "type": "message", "message": full_reply})
                        continue

                    section = _run_agent_intent(intent, routing, profile, user_id, workspace_id, message=message, history=history)
                    assistant_sections.append(section)
                except HTTPException as exc:
                    section = {"agent": intent, "type": "error", "message": str(exc.detail)}
                    assistant_sections.append(section)
                    yield _sse("section", section)
                    continue
                except Exception:
                    section = {"agent": intent, "type": "error", "message": "Something went wrong while running this step."}
                    assistant_sections.append(section)
                    yield _sse("section", section)
                    continue
                yield _sse("section", section)

            # Save assistant response
            content = next((s.get("message", "") for s in assistant_sections if s.get("type") == "message"), "")
            add_conversation_message(conversation_id, "assistant", content, sections=assistant_sections)
            yield _sse("done", {"conversation_id": conversation_id})
        except Exception:
            yield _sse("error", {"message": "The assistant could not complete your request."})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/agent/conversations")
async def create_conversation_endpoint(payload: ConversationCreateIn, user: dict = Depends(current_user)):
    title = payload.title.strip() or "New conversation"
    cid = create_conversation(user["id"], title, workspace_id=payload.workspace_id)
    return {"conversation_id": cid, "title": title}


@router.get("/agent/conversations")
async def list_conversations_endpoint(limit: int = 50, user: dict = Depends(current_user)):
    return list_conversations(user["id"], limit=limit)


@router.get("/agent/conversations/{conversation_id}")
async def get_conversation_endpoint(conversation_id: int, user: dict = Depends(current_user)):
    conv = get_conversation(conversation_id, user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(conversation_id)
    return {**conv, "messages": messages}


@router.patch("/agent/conversations/{conversation_id}")
async def update_conversation_endpoint(conversation_id: int, payload: ConversationUpdateIn, user: dict = Depends(current_user)):
    ok = update_conversation(conversation_id, user["id"], payload.dict())
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.delete("/agent/conversations/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: int, user: dict = Depends(current_user)):
    ok = delete_conversation(conversation_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.get("/automation/rules")
async def automation_rules(include_inactive: bool = False, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_automation_rules(user["id"], include_inactive=include_inactive, workspace_id=workspace_id)


@router.post("/automation/rules")
async def create_rule(payload: AutomationRuleIn, user: dict = Depends(current_user)):
    rule_id = create_automation_rule(user["id"], payload.dict(), workspace_id=payload.workspace_id)
    return {"id": rule_id, "status": "success"}


@router.put("/automation/rules/{rule_id}")
async def update_rule(rule_id: int, payload: AutomationRuleUpdate, user: dict = Depends(current_user)):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    update_automation_rule(rule_id, user["id"], data, workspace_id=getattr(payload, "workspace_id", None))
    return {"status": "success"}


@router.delete("/automation/rules/{rule_id}")
async def delete_rule(rule_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    delete_automation_rule(rule_id, user["id"], workspace_id=workspace_id)
    return {"status": "success"}


@router.post("/automation/trigger")
async def trigger_automation(payload: AutomationTriggerIn, user: dict = Depends(current_user)):
    return {"status": "success", "runs": automation_engine.trigger(user["id"], payload.trigger_event, payload.payload, workspace_id=payload.workspace_id)}


@router.get("/automation/runs")
async def automation_runs(limit: int = 100, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_automation_runs(user["id"], limit=limit, workspace_id=workspace_id)


@router.get("/automation/errors")
async def automation_errors(limit: int = 100, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_automation_errors(user["id"], limit=limit, workspace_id=workspace_id)

@router.post("/feedback")
async def submit_feedback(payload: FeedbackCreate, user: dict = Depends(current_user)):
    try:
        feedback_id = create_feedback(user["id"], payload.dict(), workspace_id=payload.workspace_id)
        return {"id": feedback_id, "status": "success", "message": "Feedback submitted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@router.get("/feedback")
async def get_my_feedback(limit: int = 100, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_feedback(user["id"], limit=limit, workspace_id=workspace_id)


@router.get("/feedback/{feedback_id}")
async def get_feedback_detail(feedback_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    feedback = get_feedback(feedback_id, user["id"], workspace_id=workspace_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback


@router.patch("/feedback/{feedback_id}/status")
async def patch_feedback_status(feedback_id: int, payload: FeedbackStatusUpdate, user: dict = Depends(current_user)):
    try:
        update_feedback_status(feedback_id, user["id"], payload.status)
        return {"status": "success", "message": "Feedback status updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audit-logs")
async def get_my_audit_logs(limit: int = 100, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_audit_logs(user["id"], limit=limit, workspace_id=workspace_id)


@router.get("/profile")
async def get_user_profile(user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"])
        return profile or {}
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get profile")


@router.post("/profile")
async def update_profile(profile_data: ProfileCreate, user: dict = Depends(current_user)):
    try:
        upsert_profile(profile_data.dict(), user["id"])
        return {"status": "success", "message": "Profile updated"}
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")


@router.get("/profiles")
async def list_user_profiles(user: dict = Depends(current_user)):
    return list_profiles(user["id"])


@router.post("/profiles")
async def create_user_profile(profile_data: ProfileCreate, make_default: bool = False, user: dict = Depends(current_user)):
    try:
        data = profile_data.dict()
        profile_id = create_profile(user["id"], data, name=data.get("name", ""), make_default=make_default)
        return {"status": "success", "id": profile_id}
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to create profile")


@router.get("/profiles/{profile_id}")
async def get_user_profile_by_id(profile_id: int, user: dict = Depends(current_user)):
    profile = get_profile(user["id"], profile_id=profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/profiles/{profile_id}")
async def update_user_profile(profile_id: int, profile_data: ProfileCreate, user: dict = Depends(current_user)):
    if not update_profile_fields(user["id"], profile_id, profile_data.dict()):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success"}


@router.post("/profiles/{profile_id}/default")
async def make_profile_default(profile_id: int, user: dict = Depends(current_user)):
    if not set_default_profile(user["id"], profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success"}


@router.delete("/profiles/{profile_id}")
async def remove_user_profile(profile_id: int, user: dict = Depends(current_user)):
    try:
        if not delete_profile(user["id"], profile_id):
            raise HTTPException(status_code=404, detail="Profile not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success"}


# Resume fields that are derived from the uploaded document. We only overwrite
# these with extracted values; user-curated preferences are preserved.
_RESUME_DERIVED_FIELDS = (
    "cv_text",
    "target_roles",
    "industries",
    "locations",
    "remote_preference",
    "work_authorization",
    "years_experience",
    "skills",
)

_MAX_RESUME_BYTES = 5 * 1024 * 1024


@router.post("/profile/upload-resume")
async def upload_resume(file: UploadFile = File(...), apply_to_profile: bool = Form(True), profile_id: Optional[int] = Form(None), user: dict = Depends(current_user)):
    """Upload a resume (.pdf/.docx/.txt), extract text + structured fields via AI,
    and (optionally) merge the extracted fields into the user's profile."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > _MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="Resume file is too large (max 5 MB).")

    try:
        cv_text = extract_text_from_upload(file.filename or "", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Resume text extraction failed: {exc}")
        raise HTTPException(status_code=400, detail="Could not read text from this file. Try a .pdf, .docx, or .txt resume.")

    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in the resume.")

    extracted = extract_profile_from_resume(cv_text, user["id"])
    extracted.pop("_ai_error", None)

    saved = False
    if apply_to_profile:
        existing = get_profile(user["id"], profile_id=profile_id) or {}
        merged = {**existing}
        for field in _RESUME_DERIVED_FIELDS:
            value = extracted.get(field)
            if value:
                merged[field] = value
        merged["resume_name"] = file.filename or merged.get("resume_name") or "resume"
        upsert_profile(merged, user["id"], profile_id=profile_id or (existing.get("id") if existing else None))
        saved = True

    return {
        "status": "success",
        "filename": file.filename,
        "applied_to_profile": saved,
        "characters": len(cv_text),
        "extracted": {field: extracted.get(field, "") for field in _RESUME_DERIVED_FIELDS},
    }


@router.get("/jobs")
async def list_all_jobs(workspace_id: Optional[int] = None, content_type: str = "job", type: Optional[str] = None, user: dict = Depends(current_user)):
    try:
        requested_type = type or content_type or "job"
        jobs = list_jobs(user["id"], workspace_id=workspace_id, content_type=requested_type)
        return jobs
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list jobs")


@router.post("/jobs")
async def create_job(job_data: JobCreate, user: dict = Depends(current_user)):
    try:
        payload = annotate_opportunity(job_data.dict())
        if not payload.get("importable"):
            raise HTTPException(status_code=400, detail=payload.get("blocked_reason") or "This item is not a valid opportunity and cannot be imported.")
        job_id = insert_job(payload, user["id"], workspace_id=job_data.workspace_id)
        return {"id": job_id, "status": "success", "message": "Job created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job")


def _filter_discovered_opportunities(items: list[dict[str, Any]], payload: DiscoveryPublicIn) -> list[dict[str, Any]]:
    keywords = " ".join(part for part in [payload.query, payload.keywords, payload.country] if part).strip().lower()
    terms = [term for term in keywords.split() if term]
    filtered: list[dict[str, Any]] = []
    for item in items:
        haystack = " ".join(str(item.get(key, "")) for key in ["title", "company", "location", "remote_type", "source", "description", "raw_text"]).lower()
        if payload.opportunity_type != "auto" and item.get("opportunity_type") not in {"", None, payload.opportunity_type}:
            continue
        if payload.remote_type != "all" and payload.remote_type.lower() not in str(item.get("remote_type", "")).lower() and payload.remote_type.lower() not in haystack:
            continue
        if payload.location.strip() and payload.location.strip().lower() not in haystack:
            continue
        if terms and not all(term in haystack for term in terms):
            continue
        if payload.opportunity_type != "auto":
            item["opportunity_type"] = payload.opportunity_type
        filtered.append(item)
    return filtered


def _profile_has_resume_context(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    return any(str(profile.get(key) or "").strip() for key in ["cv_text", "skills", "target_roles", "preferred_role"])


def _profile_search_terms(profile: dict[str, Any]) -> tuple[str, list[str]]:
    role_text = str(profile.get("preferred_role") or profile.get("target_roles") or "").strip()
    skills = [
        part.strip()
        for part in re.split(r",|\n|;", str(profile.get("skills") or ""))
        if len(part.strip()) >= 2
    ]
    industries = [
        part.strip()
        for part in re.split(r",|\n|;", str(profile.get("industries") or ""))
        if len(part.strip()) >= 2
    ]
    fallback_resume_terms = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", str(profile.get("cv_text") or ""))
        if term.lower() not in {"and", "the", "with", "for", "from", "that", "this", "resume", "experience"}
    ][:8]
    terms: list[str] = []
    if role_text:
        terms.extend(role_text.split()[:5])
    terms.extend(skills[:5])
    terms.extend(industries[:2])
    if not terms:
        terms.extend(fallback_resume_terms[:6])
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return " ".join(deduped[:8]).strip(), deduped[:12]


@router.post("/discovery/extract")
async def discovery_extract(payload: DiscoveryExtractIn, user: dict = Depends(current_user)):
    if is_job_listing_url(payload.raw):
        try:
            scraper = get_scraper_for_url(payload.raw, payload.source)
            scrape_url = indeed_url_with_work_location_intent(payload.raw, payload.work_location_filter)
            scrape_result = scraper.scrape(scrape_url)
            opportunities, skipped_location = _filter_by_work_location(scrape_result.opportunities, payload.work_location_filter)
            if not opportunities:
                raise HTTPException(
                    status_code=404,
                    detail=_url_error_detail("no_content", "No usable job content was found at the provided URL.", scraper.source_name.lower()),
                )
            return {
                "status": "success",
                "opportunities": opportunities,
                "raw_count": scrape_result.found_count,
                "work_location_filter": payload.work_location_filter,
                "jobs_found": len(opportunities),
                "jobs_skipped_location_filter": skipped_location,
                "warnings": scrape_result.warnings,
                "message": f"Found {len(opportunities)} jobs from {scraper.source_name}. Review them before importing.",
            }
        except UnsupportedSourceUrl as exc:
            raise HTTPException(
                status_code=400,
                detail=_url_error_detail("unsupported_source", str(exc)),
            )
        except ScraperError as exc:
            raise _scraper_error_response(exc, payload.source)
    try:
        source_classification = annotate_opportunity(
            {"title": payload.raw[:120], "description": payload.raw, "raw_text": payload.raw, "source": payload.source}
        )
        extracted = extract_opportunities_from_container(
            {"title": payload.raw[:120], "description": payload.raw, "raw_text": payload.raw, "source": payload.source}
        )
        if extracted:
            opportunities, skipped_location = _filter_by_work_location(extracted, payload.work_location_filter)
            return {
                "status": "success",
                "opportunities": opportunities,
                "classification": source_classification,
                "work_location_filter": payload.work_location_filter,
                "jobs_found": len(opportunities),
                "jobs_skipped_location_filter": skipped_location,
                "warnings": [] if opportunities else ["Extracted opportunities did not match the selected work-location filter."],
            }
        opportunity = extract_job_from_text(payload.raw, source=payload.source, opportunity_type=payload.opportunity_type, user_id=user["id"])
        if not opportunity.get("importable"):
            return {
                "status": "rejected",
                "opportunity": opportunity,
                "classification": opportunity,
                "work_location_filter": payload.work_location_filter,
                "jobs_found": 0,
                "jobs_skipped_location_filter": 0,
                "warnings": [opportunity.get("blocked_reason") or "No valid opportunity detected."],
            }
        opportunities, skipped_location = _filter_by_work_location([opportunity], payload.work_location_filter)
        return {
            "status": "success",
            "opportunity": opportunities[0] if opportunities else None,
            "classification": source_classification,
            "work_location_filter": payload.work_location_filter,
            "jobs_found": len(opportunities),
            "jobs_skipped_location_filter": skipped_location,
            "warnings": [] if opportunities else ["No extracted opportunity matched the selected work-location filter."],
        }
    except Exception as e:
        logger.error(f"Error extracting opportunity: {e}")
        raise HTTPException(status_code=500, detail="Failed to extract opportunity")


@router.post("/discovery/public")
async def discovery_public(payload: DiscoveryPublicIn, user: dict = Depends(current_user)):
    try:
        sources = payload.sources or ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"]
        opportunities = [annotate_opportunity(item) for item in discover_public_opportunities(payload.query, sources, payload.limit_per_source)]
        if payload.opportunity_type in {"auto", "job"}:
            opportunities = [item for item in opportunities if is_job_like(item)]
        return {"status": "success", "opportunities": _filter_discovered_opportunities(opportunities, payload)}
    except Exception as e:
        logger.error(f"Error discovering public opportunities: {e}")
        raise HTTPException(status_code=502, detail=f"Public discovery failed: {e}")


@router.post("/discovery/from-profile")
async def discovery_from_profile(payload: DiscoveryFromProfileIn, user: dict = Depends(current_user)):
    profile = get_profile(user["id"])
    if not _profile_has_resume_context(profile):
        raise HTTPException(status_code=400, detail="Add resume or profile details before finding jobs.")

    query, keywords = _profile_search_terms(profile or {})
    if not query:
        raise HTTPException(status_code=400, detail="No useful search terms were found in your profile.")

    sources = payload.sources or ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"]
    try:
        raw = discover_public_opportunities(query, sources, payload.limit_per_source)
    except Exception as exc:
        logger.error("Profile-based job discovery failed for user %s: %s", user["id"], exc)
        raise HTTPException(status_code=502, detail=f"Public discovery failed: {exc}")

    opportunities = [annotate_opportunity(item) for item in raw]
    opportunities = [item for item in opportunities if is_job_like(item)]
    if not opportunities:
        return {
            "status": "success",
            "query": query,
            "keywords": keywords,
            "opportunities": [],
            "found": 0,
            "imported": 0,
            "scored": 0,
            "using_fallback_scoring": ai_orchestrator.resolve_route(user["id"], task_type="opportunity_scoring").source == "fallback",
            "message": "No jobs were found from your profile search terms.",
        }

    using_fallback_scoring = ai_orchestrator.resolve_route(user["id"], task_type="opportunity_scoring").source == "fallback"
    scored = 0
    if payload.score_results:
        for opportunity in opportunities:
            try:
                evaluation = score_job(profile or {}, opportunity, user_id=user["id"])
                opportunity["evaluation"] = evaluation
                opportunity["match_score"] = evaluation.get("match_score")
                opportunity["score"] = evaluation.get("match_score")
                scored += 1
            except Exception as exc:
                opportunity["scoring_error"] = str(exc)
                logger.warning("Profile discovery scoring failed user_id=%s title=%s error=%s", user["id"], opportunity.get("title"), exc)
    opportunities.sort(key=lambda item: int(item.get("match_score") or -1), reverse=True)

    imported = 0
    imported_ids: list[int] = []
    warnings: list[str] = []
    errors: list[str] = []
    if payload.save_results:
        import_result = import_opportunities(opportunities, user["id"])
        imported = import_result.imported
        imported_ids = import_result.ids
        warnings = import_result.warnings
        errors = import_result.errors
        if payload.score_results and imported_ids:
            saved_jobs = [get_job(job_id, user["id"]) for job_id in imported_ids]
            for saved_job in [job for job in saved_jobs if job]:
                try:
                    evaluation = score_job(profile or {}, saved_job, user_id=user["id"])
                    save_evaluation(int(saved_job["id"]), evaluation, user["id"])
                except Exception as exc:
                    logger.warning("Profile discovery saved-job scoring failed user_id=%s job_id=%s error=%s", user["id"], saved_job.get("id"), exc)

    return {
        "status": "success" if not errors else "partial_success",
        "query": query,
        "keywords": keywords,
        "opportunities": opportunities,
        "found": len(opportunities),
        "imported": imported,
        "ids": imported_ids,
        "scored": scored,
        "using_fallback_scoring": using_fallback_scoring,
        "warnings": warnings,
        "errors": errors,
    }


@router.post("/discovery/rapidapi-linkedin")
async def discovery_rapidapi_linkedin(payload: DiscoveryRapidApiIn, user: dict = Depends(current_user)):
    settings = get_integration_settings(user["id"], "rapidapi_linkedin", workspace_id=payload.workspace_id)
    config = settings.get("config", {})
    api_key = settings.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="RapidAPI LinkedIn integration is not configured")
    try:
        items = search_linkedin_jobs(
            api_key,
            payload.title_filter,
            payload.location_filter,
            payload.offset,
            config.get("host", ""),
            config.get("endpoint", ""),
        )
        opportunities = [annotate_opportunity(item) for item in rapidapi_items_to_opportunities(items)]
        return {"status": "success", "opportunities": [item for item in opportunities if is_job_like(item)], "raw_count": len(items)}
    except Exception as e:
        logger.error(f"Error searching RapidAPI LinkedIn jobs: {e}")
        raise HTTPException(status_code=502, detail=f"LinkedIn API search failed: {e}")


@router.post("/discovery/apify")
async def discovery_apify(payload: DiscoveryApifyIn, user: dict = Depends(current_user)):
    settings = get_integration_settings(user["id"], "apify", workspace_id=payload.workspace_id)
    config = settings.get("config", {})
    api_key = settings.get("api_key", "")
    actor_id = config.get("actor_id", "")
    if not api_key or not actor_id:
        raise HTTPException(status_code=400, detail="Apify integration is not configured")
    try:
        run_input = build_run_input(payload.url, config.get("input_template", ""))
        items = run_actor_for_items(api_key, actor_id, run_input)
        opportunities = [annotate_opportunity(item) for item in apify_items_to_opportunities(items, source=f"Apify:{actor_id}")]
        return {"status": "success", "opportunities": [item for item in opportunities if is_job_like(item)], "raw_count": len(items)}
    except Exception as e:
        logger.error(f"Error running Apify discovery: {e}")
        raise HTTPException(status_code=502, detail=f"Apify scraper failed: {e}")


@router.post("/discovery/import-url")
async def discovery_import_url(payload: DiscoveryImportUrlIn, user: dict = Depends(current_user)):
    if not is_job_listing_url(payload.url):
        raise HTTPException(
            status_code=400,
            detail=_url_error_detail(
                "unsupported_source",
                "Invalid or unsupported listing URL. Use a supported job listing URL or paste the job details manually.",
            ),
        )
    try:
        scraper = get_scraper_for_url(payload.url, payload.source)
        scrape_url = indeed_url_with_work_location_intent(payload.url, payload.work_location_filter)
        scrape_result = scraper.scrape(scrape_url, page_limit=payload.page_limit)
        opportunities, skipped_location = _filter_by_work_location(scrape_result.opportunities, payload.work_location_filter)
        if not opportunities:
            raise HTTPException(
                status_code=404,
                detail=_url_error_detail("no_content", "No usable job content was found at the provided URL.", scraper.source_name.lower()),
            )
        import_result = import_opportunities(opportunities, user["id"], workspace_id=payload.workspace_id)
        return {
            "status": "success" if not import_result.errors else "partial_success",
            "source": scraper.source_name,
            "page_urls": scrape_result.page_urls,
            "work_location_filter": payload.work_location_filter,
            "jobs_found": import_result.found,
            "jobs_imported": import_result.imported,
            "jobs_skipped_duplicates": import_result.skipped_duplicates,
            "jobs_skipped_location_filter": skipped_location,
            "found": import_result.found,
            "imported": import_result.imported,
            "skipped_duplicates": import_result.skipped_duplicates,
            "errors": import_result.errors,
            "warnings": [*scrape_result.warnings, *import_result.warnings],
            "ids": import_result.ids,
        }
    except HTTPException:
        raise
    except UnsupportedSourceUrl as exc:
        raise HTTPException(
            status_code=400,
            detail=_url_error_detail("unsupported_source", str(exc)),
        )
    except ScraperError as exc:
        raise _scraper_error_response(exc, payload.source)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_url_error_detail("invalid_url", str(exc) or "Invalid URL. Please check the link and try again."),
        )


@router.post("/discovery/import")
async def discovery_import(payload: DiscoveryImportIn, user: dict = Depends(current_user)):
    result = import_opportunities(payload.opportunities, user["id"], workspace_id=payload.workspace_id)
    if result.errors and not result.imported:
        logger.error(f"Error importing discovered opportunities: {result.errors}")
        raise HTTPException(status_code=500, detail="Failed to import discovered opportunities")
    return {
        "status": "success" if not result.errors else "partial_success",
        "ids": result.ids,
        "count": result.imported,
        "found": result.found,
        "imported": result.imported,
        "skipped_duplicates": result.skipped_duplicates,
        "errors": result.errors,
        "warnings": result.warnings,
    }


@router.post("/jobs/cleanup-non-opportunities")
async def cleanup_non_opportunities(workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return {"status": "success", **cleanup_non_opportunity_records(user["id"], workspace_id=workspace_id)}


@router.get("/jobs/{job_id}")
async def get_job_detail(job_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        job = get_job(job_id, user["id"], workspace_id=workspace_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to get job")


@router.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        job = get_job(job_id, user["id"], workspace_id=workspace_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        delete_job(job_id, user["id"], workspace_id=workspace_id)
        return {"status": "success", "message": "Job deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete job")


@router.post("/jobs/{job_id}/score")
async def score_single_job(job_id: int, profile_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"], profile_id=profile_id)
        if not profile:
            raise HTTPException(status_code=400, detail="Profile not configured")

        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        gate = scoring_gate(job)
        if not gate.importable:
            raise HTTPException(status_code=400, detail="This item is not a valid opportunity and cannot be scored.")

        evaluation = score_job(profile, job, user_id=user["id"])
        save_evaluation(job_id, evaluation, user["id"])
        return evaluation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scoring job: {e}")
        raise HTTPException(status_code=500, detail="Failed to score job")


@router.post("/jobs/score-batch")
async def score_jobs_batch(payload: BatchScoreIn, user: dict = Depends(current_user)):
    profile = get_profile(user["id"], profile_id=payload.profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Add your resume profile before scoring jobs.")

    candidate_jobs = list_jobs(user["id"], content_type="job")
    ids = [int(job_id) for job_id in payload.job_ids]
    if payload.score_all_unscored:
        ids = [int(job["job_id"]) for job in candidate_jobs if job.get("match_score") is None]
    if not ids:
        detail = "No unscored jobs are available for scoring." if payload.score_all_unscored else "Select at least one job to score."
        raise HTTPException(status_code=400, detail=detail)

    route = ai_orchestrator.resolve_route(user["id"], task_type="opportunity_scoring")
    using_fallback_scoring = route.source == "fallback"
    logger.info(
        "Starting bulk job scoring user_id=%s requested=%s score_all_unscored=%s fallback_scoring=%s",
        user["id"],
        len(ids),
        payload.score_all_unscored,
        using_fallback_scoring,
    )
    results = []
    for job_id in ids:
        try:
            job = get_job(int(job_id), user["id"])
            if not job:
                results.append({"job_id": job_id, "status": "failed", "error": "Job not found"})
                logger.warning("Bulk scoring failed: job not found user_id=%s job_id=%s", user["id"], job_id)
                continue
            title = str(job.get("title") or f"Job {job_id}")
            if not is_job_like(job):
                reason = "Only jobs, internships, contracts, and freelance roles can be bulk scored."
                results.append({
                    "job_id": job_id,
                    "title": title,
                    "status": "skipped",
                    "classification": job.get("classification") or job.get("opportunity_type") or "unknown",
                    "reason": reason,
                })
                logger.info("Bulk scoring skipped non-job user_id=%s job_id=%s reason=%s", user["id"], job_id, reason)
                continue
            if not str(job.get("description") or job.get("raw_text") or "").strip():
                reason = "Job description is missing."
                results.append({"job_id": job_id, "title": title, "status": "skipped", "reason": reason})
                logger.info("Bulk scoring skipped missing description user_id=%s job_id=%s", user["id"], job_id)
                continue
            gate = scoring_gate(job)
            if not gate.importable:
                reason = gate.blocked_reason or gate.reason or "This saved item is not ready to score."
                results.append({
                    "job_id": job_id,
                    "title": title,
                    "status": "skipped",
                    "classification": gate.classification,
                    "reason": reason,
                })
                logger.info("Bulk scoring skipped gated job user_id=%s job_id=%s reason=%s", user["id"], job_id, reason)
                continue
            evaluation = score_job(profile, job, user_id=user["id"])
            save_evaluation(int(job_id), evaluation, user["id"])
            results.append({"job_id": job_id, "title": title, "status": "success", "evaluation": evaluation})
        except Exception as exc:
            logger.error("Batch scoring failed for job %s: %s", job_id, exc)
            results.append({"job_id": job_id, "status": "failed", "error": str(exc)})
    succeeded = len([item for item in results if item["status"] == "success"])
    skipped = len([item for item in results if item["status"] == "skipped"])
    failed = len([item for item in results if item["status"] == "failed"])
    logger.info(
        "Bulk job scoring completed user_id=%s requested=%s scored=%s skipped=%s failed=%s",
        user["id"],
        len(ids),
        succeeded,
        skipped,
        failed,
    )
    return {
        "status": "success" if failed == 0 and skipped == 0 else "partial_success",
        "total": len(results),
        "total_requested": len(ids),
        "succeeded": succeeded,
        "scored": succeeded,
        "skipped": skipped,
        "failed": failed,
        "using_fallback_scoring": using_fallback_scoring,
        "results": results,
    }


def _generate_resume_review(profile: dict[str, Any], job: dict[str, Any] | None, resume_text: str = "", target_role: str = "") -> dict[str, Any]:
    resume = resume_text.strip() or str(profile.get("cv_text") or "")
    job = job or {}
    context = build_job_context(profile, job)
    primary_focus = choose_primary_focus_area(context["focus_areas"])
    profile_terms = {term.lower() for term in extract_profile_skills(profile, limit=20)}
    missing = sorted(
        list(
            {keyword.lower() for keyword in context["keywords"]}
            .difference(profile_terms)
            & {"python", "react", "next.js", "sql", "aws", "azure", "fastapi", "typescript", "leadership", "analytics", "openai", "claude", "zapier", "n8n"}
        )
    )
    return {
        "summary": f"Resume review for {target_role or job.get('title') or profile.get('preferred_role') or 'target role'}.",
        "strengths": [
            "Existing resume/profile text is available for tailoring." if resume else "Add resume text to unlock stronger feedback.",
            f"Profile skills can be mapped into {primary_focus.lower()} language.",
        ],
        "weaknesses": [
            "Quantify recent achievements with business or delivery impact.",
            f"Move the most relevant keywords for {context['title']} into the top third of the resume.",
        ],
        "missing_keywords": missing,
        "job_focus_areas": context["focus_areas"],
        "job_highlights": context["highlights"],
        "formatting_suggestions": [
            "Use concise bullets that start with action verbs.",
            "Keep sections scan-friendly for ATS and recruiter review.",
        ],
        "role_alignment": f"Good baseline alignment; improve by mirroring the {context['title']} title, core stack, and responsibility language.",
        "recommended_changes": [
            f"Add 2-3 bullets tied directly to {primary_focus.lower()} job responsibilities.",
            "Replace generic summaries with target-role positioning.",
        ],
        "improved_resume_response": f"Draft improvement: emphasize measurable outcomes, relevant tools, and the exact {context['title']} target role in the summary and first experience section.",
    }


def _keywords_from_job(job: dict[str, Any]) -> list[str]:
    text = " ".join(str(job.get(key) or "") for key in ["title", "description", "raw_text"])
    important = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", text)
        if term.lower() not in {"and", "the", "with", "for", "from", "that", "this", "you", "our", "are", "will", "role", "job"}
    ]
    seen: set[str] = set()
    keywords: list[str] = []
    for term in important:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(term)
    return keywords[:18]


def _generate_tailored_resume(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    context = build_job_context(profile, job)
    role = context["title"]
    company = context["company"]
    skills = context["skills"]
    keywords = context["keywords"]
    focus_areas = context["focus_areas"]
    highlights = context["highlights"]
    emphasized_skills = [skill for skill in skills if skill.lower() in " ".join(keywords).lower()] or skills[:8] or keywords[:8]
    primary_focus = choose_primary_focus_area(focus_areas)
    secondary_focus = next((area for area in focus_areas if area != primary_focus), primary_focus)
    highlight = highlights[0] if highlights else ""
    summary = (
        f"{profile.get('years_experience') or 'Experienced'} professional targeting {role} at {company}, "
        f"with hands-on experience in {', '.join(emphasized_skills[:5]) or 'the role requirements'} and a clear fit for {primary_focus.lower()}."
    )
    bullets = [
        f"Delivered work aligned with {primary_focus.lower()} using {', '.join(emphasized_skills[:4]) or 'relevant tools and practices'}.",
        f"Translated {secondary_focus.lower()} requirements into maintainable, measurable solutions that can be referenced in the {role} resume.",
        f"Collaborated across stakeholders to ship reliable improvements; job-specific cue: {highlight[:120] or 'highlight the most relevant project outcome from your history'}.",
    ]
    draft = "\n".join(
        [
            "Professional Summary",
            summary,
            "",
            "Selected Experience Bullets",
            *[f"- {bullet}" for bullet in bullets],
            "",
            "Skills",
            ", ".join(emphasized_skills[:12] or keywords[:12]),
        ]
    )
    return {
        "type": "tailored_resume",
        "target_role": role,
        "company": company,
        "tailored_summary": summary,
        "tailored_experience_bullets": bullets,
        "skills_to_emphasize": emphasized_skills[:12],
        "keywords_to_include": keywords,
        "job_focus_areas": focus_areas,
        "job_highlights": highlights,
        "optional_cover_note": f"I am interested in the {role} role at {company} because the posting emphasizes {primary_focus.lower()} and {secondary_focus.lower()}, which maps directly to my background.",
        "application_guidance": [
            "Keep claims grounded in your real resume and project history.",
            "Add metrics to the bullets before submitting.",
            "Mirror the most relevant job keywords where they truthfully match your experience.",
        ],
        "resume_draft": draft,
        "generation_source": "local_fallback",
    }


def _resume_draft_to_text(draft: Any) -> str:
    """Flatten a resume_draft into copy-ready text. The model occasionally
    returns a structured object (name/summary/experience/...) instead of a
    string, which the UI cannot render directly."""
    if draft is None:
        return ""
    if isinstance(draft, str):
        return draft
    if isinstance(draft, (list, tuple)):
        return "\n".join(_resume_draft_to_text(item) for item in draft if item is not None)
    if isinstance(draft, dict):
        lines: list[str] = []
        for key, value in draft.items():
            label = str(key).replace("_", " ").title()
            text = _resume_draft_to_text(value)
            if not text.strip():
                continue
            if "\n" in text:
                lines.append(f"{label}:\n{text}")
            else:
                lines.append(f"{label}: {text}")
        return "\n\n".join(lines)
    return str(draft)


def _llm_tailored_resume(profile: dict[str, Any], job: dict[str, Any], user_id: int) -> dict[str, Any]:
    fallback = _generate_tailored_resume(profile, job)
    route = ai_orchestrator.resolve_route(user_id, task_type="resume_tailoring")
    job_context = build_job_context(profile, job)
    system = (
        "You are an expert resume writer. Return JSON only. Create a truthful tailored resume draft grounded only in "
        "the supplied resume/profile and job description. Do not invent employers, degrees, certifications, metrics, or credentials."
    )
    context = {
        "resume_text": profile.get("cv_text") or "",
        "profile": profile,
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "description": job.get("description") or job.get("raw_text") or "",
            "location": job.get("location"),
            "remote_type": job.get("remote_type"),
            "keywords": job_context["keywords"],
            "focus_areas": job_context["focus_areas"],
            "highlights": job_context["highlights"],
        },
        "required_output_keys": [
            "tailored_summary",
            "tailored_experience_bullets",
            "skills_to_emphasize",
            "keywords_to_include",
            "optional_cover_note",
            "application_guidance",
            "resume_draft",
        ],
    }
    tailored = ai_orchestrator.ask_json(
        system,
        json.dumps(context),
        fallback,
        user_id=user_id,
        task_type="resume_tailoring",
        workspace_id=job.get("workspace_id"),
    )
    for key, value in fallback.items():
        tailored.setdefault(key, value)
    # The model sometimes returns resume_draft as a structured object instead of
    # a copy-ready string; flatten it so the UI can render it as text.
    tailored["resume_draft"] = _resume_draft_to_text(tailored.get("resume_draft"))
    tailored["type"] = "tailored_resume"
    tailored["target_role"] = tailored.get("target_role") or job.get("title") or "target role"
    tailored["company"] = tailored.get("company") or job.get("company") or ""
    tailored["using_fallback"] = route.source == "fallback" or bool(tailored.get("_ai_error"))
    tailored["generation_source"] = "local_fallback" if tailored["using_fallback"] else "llm"
    if tailored.get("_ai_error"):
        tailored["ai_error"] = "AI generation failed; local fallback was used."
        tailored.pop("_ai_error", None)
    return tailored


def _generate_interview_prep(profile: dict[str, Any], job: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    context = build_job_context(profile, job)
    role = context["title"]
    company = context["company"]
    focus_areas = context["focus_areas"]
    highlights = context["highlights"]
    skills = context["skills"]
    primary_focus = choose_primary_focus_area(focus_areas)
    other_focuses = [area for area in focus_areas if area != primary_focus]
    secondary_focus = other_focuses[0] if other_focuses else primary_focus
    third_focus = other_focuses[1] if len(other_focuses) > 1 else primary_focus
    skill_line = ", ".join(skills[:4] or context["keywords"][:4] or ["your stack"])
    highlight_line = highlights[0] if highlights else f"the requirements for {role}"
    return {
        "summary": f"Interview preparation for {role} at {company}.",
        "behavioral_questions": [
            f"Tell me about a time you delivered {primary_focus.lower()} under a tight timeline.",
            f"Describe a situation where you had to balance {secondary_focus.lower()} with quality or stakeholder expectations.",
            f"Give an example of improving a process or system similar to the work described in this posting.",
        ],
        "technical_questions": [
            f"Walk through how your skills in {skill_line} apply to {primary_focus.lower()} for this role.",
            f"How would you approach a production issue that touches {secondary_focus.lower()} and needs careful validation?",
            f"What tradeoffs would you consider when designing a solution for {third_focus.lower()} in a fast-moving environment?",
        ],
        "role_specific_questions": [
            f"What attracts you to the {role} responsibilities at {company}?",
            f"Which requirement in the job description best matches your recent experience with {primary_focus.lower()}?",
        ],
        "company_job_specific_questions": [
            f"The posting highlights: {highlight_line[:140]}. How would you show direct experience with that?",
            f"What part of the {role} role at {company} feels most aligned with your background?",
        ],
        "suggested_answer_outlines": [
            f"Use STAR, then close by tying the answer back to {primary_focus.lower()} and the impact you delivered.",
            f"Reference a concrete project that shows {secondary_focus.lower()} and keep the answer under two minutes.",
        ],
        "star_format_guidance": [
            "Situation: give only the minimum context needed.",
            "Task: state the goal or constraint clearly.",
            "Action: focus on what you personally did.",
            "Result: include a measurable or observable outcome.",
        ],
        "weakness_improvement_prompts": [
            f"Prepare one example that proves you can handle {primary_focus.lower()} without inventing details.",
            f"Prepare one example that proves you can communicate tradeoffs around {secondary_focus.lower()}.",
        ],
        "candidate_questions": [
            f"What does success look like for {role} in the first 30, 60, and 90 days?",
            f"Where does {company} need the most help relative to {highlight_line[:90]}?",
        ],
        "final_preparation_checklist": [
            f"Have one example ready for {primary_focus.lower()}",
            f"Have one example ready for {secondary_focus.lower()}",
            "Prepare one metric-driven story and one learning story.",
            "Review the company, the job description, and your resume side by side before the interview.",
        ],
        "talking_points": [
            evaluation.get("good_fit") or f"Highlight direct overlap between your experience and the {role} responsibilities.",
            f"Prepare one metric-driven achievement and one story tied to {primary_focus.lower()}.",
        ],
        "questions_to_ask": [
            "What would success look like in the first 90 days?",
            f"Which team priorities are driving this opening at {company}?",
        ],
        "generation_source": "local_fallback",
    }


def _require_ai_configuration(user_id: int, task_type: str) -> None:
    route = ai_orchestrator.resolve_route(user_id, task_type=task_type)
    if not (route.settings.get("api_key") or "").strip():
        raise HTTPException(
            status_code=400,
            detail="LLM provider configuration is missing in database settings. Configure an active AI provider before generating this output.",
        )


def _llm_resume_review(profile: dict[str, Any], job: dict[str, Any] | None, resume_text: str, target_role: str, user_id: int) -> dict[str, Any]:
    _require_ai_configuration(user_id, "resume_review")
    fallback = _generate_resume_review(profile, job, resume_text, target_role)
    system = (
        "You are an expert resume reviewer. Return JSON only with keys: overall_assessment, strengths, weaknesses, "
        "missing_keywords, role_alignment_feedback, formatting_suggestions, ats_improvement_suggestions, "
        "recommended_bullet_rewrites, summary_rewrite_suggestion, priority_action_list, final_improved_resume_guidance."
    )
    context = {
        "user_profile": profile,
        "target_role": target_role or (job or {}).get("title") or profile.get("preferred_role") or profile.get("target_roles"),
        "selected_opportunity": job or {},
        "resume_text": resume_text or profile.get("cv_text") or "",
        "user_preferences": {
            "country": profile.get("country"),
            "role": profile.get("preferred_role") or profile.get("target_roles"),
            "job_type": profile.get("job_preferences"),
            "remote_preference": profile.get("remote_preference"),
            "platforms": profile.get("platforms"),
        },
    }
    review = ai_orchestrator.ask_json(
        system,
        json.dumps(context),
        fallback,
        user_id=user_id,
        task_type="resume_review",
        workspace_id=job.get("workspace_id") if job else None,
    )
    if review.get("_ai_error"):
        raise HTTPException(status_code=502, detail=f"LLM resume review failed: {review.get('_ai_error')}")
    review.setdefault("generation_source", "llm")
    return review


def _llm_interview_prep(profile: dict[str, Any], job: dict[str, Any], evaluation: dict[str, Any], user_id: int) -> dict[str, Any]:
    _require_ai_configuration(user_id, "interview_prep")
    fallback = _generate_interview_prep(profile, job, evaluation)
    latest_reviews = list_resume_reviews(user_id, job_id=int(job["id"]), limit=1)
    job_context = build_job_context(profile, job)
    system = (
        "You are an expert interview coach. Return JSON only with keys: behavioral_questions, technical_questions, "
        "role_specific_questions, company_job_specific_questions, suggested_answer_outlines, star_format_guidance, "
        "weakness_improvement_prompts, candidate_questions, final_preparation_checklist."
    )
    context = {
        "user_profile": profile,
        "resume_text": profile.get("cv_text") or "",
        "selected_opportunity": job,
        "company_name": job.get("company"),
        "role_title": job.get("title"),
        "job_description": job.get("description"),
        "required_skills": job.get("raw_text") or job.get("description"),
        "job_keywords": job_context["keywords"],
        "job_focus_areas": job_context["focus_areas"],
        "job_highlights": job_context["highlights"],
        "ai_score": evaluation,
        "resume_review_findings": latest_reviews[0] if latest_reviews else {},
    }
    prep = ai_orchestrator.ask_json(
        system,
        json.dumps(context),
        fallback,
        user_id=user_id,
        task_type="interview_prep",
        workspace_id=job.get("workspace_id"),
    )
    if prep.get("_ai_error"):
        raise HTTPException(status_code=502, detail=f"LLM interview preparation failed: {prep.get('_ai_error')}")
    prep.setdefault("generation_source", "llm")
    return prep


@router.post("/profile/resume-review")
async def post_profile_resume_review(payload: ResumeReviewIn, user: dict = Depends(current_user)):
    profile = get_profile(user["id"])
    if not profile and not payload.resume_text.strip():
        raise HTTPException(status_code=400, detail="Profile or resume text is required")
    job = get_job(payload.job_id, user["id"]) if payload.job_id else None
    review = _llm_resume_review(profile or {}, job, payload.resume_text, payload.target_role, user["id"])
    return save_resume_review(user["id"], review, payload.job_id)


@router.get("/profile/resume-reviews")
async def get_profile_resume_reviews(job_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_resume_reviews(user["id"], job_id=job_id)


@router.post("/jobs/{job_id}/resume-review")
async def post_job_resume_review(job_id: int, payload: ResumeReviewIn, user: dict = Depends(current_user)):
    payload.job_id = job_id
    return await post_profile_resume_review(payload, user)


@router.post("/jobs/{job_id}/tailor-resume")
async def post_job_tailored_resume(job_id: int, profile_id: Optional[int] = None, user: dict = Depends(current_user)):
    profile = get_profile(user["id"], profile_id=profile_id)
    if not _profile_has_resume_context(profile):
        raise HTTPException(status_code=400, detail="Add resume or profile details before tailoring a resume.")
    job = get_job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not str(job.get("description") or job.get("raw_text") or "").strip():
        raise HTTPException(status_code=400, detail="This job does not have enough description detail to tailor a resume.")
    tailored = _llm_tailored_resume(profile or {}, job, user["id"])
    return save_resume_review(user["id"], tailored, job_id)


def _fallback_resume_structure(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Best-effort structured resume from profile fields when AI is unavailable."""
    skills = [s.strip() for s in str(profile.get("skills") or "").split(",") if s.strip()]
    return {
        "full_name": profile.get("full_name") or "Your Name",
        "headline": job.get("title") or profile.get("preferred_role") or profile.get("target_roles") or "",
        "contact": {
            "email": profile.get("email") or "",
            "location": profile.get("locations") or profile.get("country") or "",
            "phone": "",
            "linkedin": "",
            "website": "",
        },
        "summary": (str(profile.get("cv_text") or "").strip()[:600]) or "Experienced professional aligned to the target role.",
        "skills": skills,
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
    }


def _llm_structured_resume(profile: dict[str, Any], job: dict[str, Any], user_id: int) -> dict[str, Any]:
    fallback = _fallback_resume_structure(profile, job)
    job_context = build_job_context(profile, job)
    system = (
        "You are an expert resume writer. Return JSON only describing a truthful, ATS-friendly resume tailored to the "
        "target job, grounded strictly in the supplied resume text and profile. Do NOT invent employers, job titles, "
        "dates, degrees, certifications, or metrics that are not present in the source. Leave fields empty if unknown."
    )
    context = {
        "resume_text": profile.get("cv_text") or "",
        "profile": profile,
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "description": job.get("description") or job.get("raw_text") or "",
            "keywords": job_context["keywords"],
            "focus_areas": job_context["focus_areas"],
        },
        "output_schema": {
            "full_name": "string",
            "headline": "string (target job title)",
            "contact": {"email": "string", "phone": "string", "location": "string", "linkedin": "string", "website": "string"},
            "summary": "string (3-4 sentence professional summary tailored to the job)",
            "skills": ["string"],
            "experience": [{"title": "string", "company": "string", "location": "string", "start": "string", "end": "string", "bullets": ["string"]}],
            "education": [{"degree": "string", "institution": "string", "location": "string", "year": "string"}],
            "certifications": ["string"],
            "projects": [{"name": "string", "description": "string"}],
        },
        "required_output_keys": RESUME_STRUCTURE_KEYS,
    }
    structure = ai_orchestrator.ask_json(
        system,
        json.dumps(context),
        fallback,
        user_id=user_id,
        task_type="resume_document",
        workspace_id=job.get("workspace_id"),
    )
    if structure.get("_ai_error"):
        structure = fallback
    # Backfill any keys the model omitted so rendering never KeyErrors.
    for key in RESUME_STRUCTURE_KEYS:
        structure.setdefault(key, fallback.get(key))
    return structure


@router.get("/resume-templates")
async def get_resume_templates(user: dict = Depends(current_user)):
    return RESUME_TEMPLATES


@router.post("/jobs/{job_id}/resume-document")
async def build_resume_document(job_id: int, template: str = "international", profile_id: Optional[int] = None, user: dict = Depends(current_user)):
    if not is_valid_template(template):
        raise HTTPException(status_code=400, detail="Unknown resume template.")
    profile = get_profile(user["id"], profile_id=profile_id)
    if not _profile_has_resume_context(profile):
        raise HTTPException(status_code=400, detail="Add resume or profile details before building a resume.")
    job = get_job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not str(job.get("description") or job.get("raw_text") or "").strip():
        raise HTTPException(status_code=400, detail="This job does not have enough description detail to build a resume.")

    structure = _llm_structured_resume(profile or {}, job, user["id"])
    try:
        docx_bytes = render_resume_docx(structure, template)
    except Exception as exc:
        logger.error(f"Resume document rendering failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to build the resume document.")

    safe_company = re.sub(r"[^A-Za-z0-9]+", "-", str(job.get("company") or job.get("title") or "resume")).strip("-").lower() or "resume"
    filename = f"resume-{safe_company}-{template}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/jobs/{job_id}/interview-prep")
async def post_job_interview_prep(job_id: int, user: dict = Depends(current_user)):
    profile = get_profile(user["id"])
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not configured")
    job = get_job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    evaluation = get_evaluation(job_id, user["id"])
    if not evaluation:
        try:
            evaluation = score_job(profile, job, user_id=user["id"])
        except Exception:
            evaluation = {
                "match_score": 0,
                "priority": "Low",
                "good_fit": "Highlight direct overlap between your experience and the job.",
                "weak_areas": "Review the job description and practice concrete examples.",
                "red_flags": "No automated score was available.",
            }
    fallback = _generate_interview_prep(profile, job, evaluation)
    generation_source = "local_fallback"
    try:
        prep = _llm_interview_prep(profile, job, evaluation, user["id"])
        generation_source = "llm"
    except HTTPException:
        prep = fallback
    except Exception:
        prep = fallback
    prep.setdefault("generation_source", generation_source)
    return save_interview_prep(user["id"], job_id, prep)


@router.get("/jobs/{job_id}/interview-prep")
async def get_job_interview_prep(job_id: int, user: dict = Depends(current_user)):
    return list_interview_prep(user["id"], job_id=job_id)


@router.post("/recordings")
async def post_recording(payload: RecordingIn, user: dict = Depends(current_user)):
    if not payload.data_url.startswith("data:audio/"):
        raise HTTPException(status_code=400, detail="Recording payload must be an audio data URL")
    recording = payload.dict()
    recording["storage_type"] = "legacy_data_url"
    recording["playback_url"] = payload.data_url
    return save_recording(user["id"], recording, job_id=payload.job_id)


@router.post("/recordings/upload")
async def upload_recording(
    job_id: Optional[int] = Form(default=None),
    title: str = Form(default="Interview practice recording"),
    duration_ms: int = Form(default=0),
    interview_prep_session_id: Optional[int] = Form(default=None),
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    config = _recording_storage_config(user["id"])
    mime_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if mime_type not in set(config["allowed_mime_types"]):
        raise HTTPException(status_code=400, detail=f"Recording type '{mime_type}' is not allowed.")
    content = await file.read()
    if len(content) > int(config["max_upload_size"]):
        raise HTTPException(status_code=413, detail="Recording exceeds the configured maximum upload size.")
    base_dir = Path(config["storage_path"]).expanduser().resolve()
    user_dir = (base_dir / str(user["id"])).resolve()
    if not str(user_dir).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid recording storage path.")
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(file.filename or "recording").stem).strip("-")[:80] or "recording"
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(8)}-{safe_title}{_safe_audio_extension(file.filename or '', mime_type)}"
    stored_path = (user_dir / stored_name).resolve()
    if not str(stored_path).startswith(str(user_dir)):
        raise HTTPException(status_code=400, detail="Invalid recording filename.")
    stored_path.write_bytes(content)
    playback_url = f"/api/v1/recordings/{stored_name}/file"
    recording = {
        "title": title,
        "mime_type": mime_type,
        "data_url": "",
        "duration_ms": duration_ms,
        "interview_prep_session_id": interview_prep_session_id,
        "original_filename": file.filename or "",
        "stored_path": str(stored_path),
        "playback_url": playback_url,
        "file_size": len(content),
        "storage_type": config["storage_type"],
    }
    return save_recording(user["id"], recording, job_id=job_id)


@router.get("/recordings")
async def get_recordings(job_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_recordings(user["id"], job_id=job_id)


@router.get("/recordings/{filename}/file")
async def get_recording_file(filename: str, user: dict = Depends(current_user)):
    rows = list_recordings(user["id"], limit=500)
    for row in rows:
        stored_path = row.get("stored_path") or ""
        if stored_path and Path(stored_path).name == filename:
            path = Path(stored_path)
            if not path.exists():
                raise HTTPException(status_code=404, detail="Recording file not found")
            return FileResponse(path, media_type=row.get("mime_type") or "audio/webm", filename=row.get("original_filename") or filename)
    raise HTTPException(status_code=404, detail="Recording not found")


@router.get("/gmail/status")
async def get_gmail_status(user: dict = Depends(current_user)):
    connection = get_gmail_connection(user["id"])
    return {**connection, "status": "connected" if connection.get("connected") else ("configured" if connection.get("configured") else "not_configured")}


@router.get("/gmail/auth-url")
async def get_gmail_auth_url(user: dict = Depends(current_user)):
    try:
        return {"url": build_gmail_authorization_url(user["id"])}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/gmail/oauth/callback")
async def gmail_oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "error", "message": error}))
    if not code or not state:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "error", "message": "missing_oauth_callback_values"}))
    try:
        parts = state.split(":")
        if len(parts) < 3 or parts[0] != "gmail":
            raise RuntimeError("Invalid Gmail OAuth state.")
        user_id = int(parts[1])
        settings = get_integration_settings(user_id, "gmail")
        redirect_uri = (settings.get("config") or {}).get("redirect_uri")
        exchange_gmail_code(user_id, code, redirect_uri, state)
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "connected"}))
    except Exception as exc:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "error", "message": str(exc)}))


@router.post("/gmail/disconnect")
async def post_gmail_disconnect(user: dict = Depends(current_user)):
    disconnect_gmail(user["id"])
    return {"status": "success", "connected": False}


@router.get("/gmail/messages")
async def get_gmail_messages(limit: int = 50, user: dict = Depends(current_user)):
    return list_gmail_messages(user["id"], limit=limit)


@router.post("/gmail/messages")
async def post_gmail_messages(payload: GmailMessagesIn, user: dict = Depends(current_user)):
    return {"status": "success", "messages": save_gmail_messages(user["id"], payload.messages)}


@router.post("/jobs/{job_id}/generate-materials")
async def generate_job_materials(job_id: int, user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"])
        if not profile:
            raise HTTPException(status_code=400, detail="Profile not configured")

        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        evaluation = get_evaluation(job_id, user["id"])
        if not evaluation:
            evaluation = score_job(profile, job, user_id=user["id"])
            save_evaluation(job_id, evaluation, user["id"])

        materials = generate_materials(profile, job, evaluation, user_id=user["id"], workspace_id=job.get("workspace_id"))
        save_materials(job_id, materials, user["id"])
        return materials
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating materials: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate materials")


@router.get("/jobs/{job_id}/materials")
async def get_job_materials(job_id: int, user: dict = Depends(current_user)):
    try:
        materials = get_materials(job_id, user["id"])
        return materials or {}
    except Exception as e:
        logger.error(f"Error getting materials: {e}")
        raise HTTPException(status_code=500, detail="Failed to get materials")


@router.patch("/jobs/{job_id}/status")
async def update_job_status(job_id: int, status: str, notes: str = "", user: dict = Depends(current_user)):
    try:
        update_status(job_id, status, notes, user["id"])
        return {"status": "success", "message": "Job status updated"}
    except Exception as e:
        logger.error(f"Error updating status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update status")


@router.get("/posts")
async def get_posts(workspace_id: Optional[int] = None, limit: int = 100, user: dict = Depends(current_user)):
    return list_posts(user["id"], workspace_id=workspace_id, limit=limit)


@router.post("/posts")
async def post_create(payload: PostCreate, user: dict = Depends(current_user)):
    post_id = create_post(user["id"], payload.dict(), workspace_id=payload.workspace_id)
    return {"id": post_id, "status": "success"}


@router.post("/posts/{post_id}/approve")
async def post_approve(post_id: int, user: dict = Depends(current_user)):
    try:
        approve_post(user["id"], post_id)
        return {"status": "success"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/posts/{post_id}/publish")
async def post_publish(post_id: int, payload: PublishRequest, user: dict = Depends(current_user)):
    try:
        return publish_post(user["id"], post_id, dry_run=payload.dry_run)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/publishing/validate")
async def publishing_validate(platform: str, content: str, media_count: int = 0, user: dict = Depends(current_user)):
    result = validate_target(platform, content, media_count=media_count)
    return {"ok": result.ok, "errors": result.errors, "warnings": result.warnings}


@router.get("/reminders")
async def list_reminders(user: dict = Depends(current_user)):
    try:
        reminders = due_reminders(user["id"])
        return reminders
    except Exception as e:
        logger.error(f"Error listing reminders: {e}")
        raise HTTPException(status_code=500, detail="Failed to list reminders")


@router.post("/reminders")
async def create_reminder_endpoint(reminder_data: ReminderCreate, user: dict = Depends(current_user)):
    try:
        create_reminder(
            reminder_data.job_id,
            reminder_data.kind,
            reminder_data.remind_at,
            reminder_data.note or "",
            user["id"],
        )
        return {"status": "success", "message": "Reminder created"}
    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create reminder")


@router.post("/data/clear")
async def clear_my_data(user: dict = Depends(current_user)):
    try:
        delete_user_data(user["id"])
        return {"status": "success", "message": "Your data was deleted"}
    except Exception as e:
        logger.error(f"Error clearing data: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear data")


@router.post("/compliance/export")
async def compliance_export(workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return export_user_data(user["id"], workspace_id=workspace_id)


@router.get("/compliance/exports")
async def compliance_exports(limit: int = 100, user: dict = Depends(current_user)):
    return list_compliance_exports(user["id"], limit=limit)


@router.post("/compliance/deletion-request")
async def compliance_deletion_request(payload: DeletionRequestIn, user: dict = Depends(current_user)):
    alert_id = request_user_deletion(user["id"], payload.reason)
    return {"status": "review_requested", "alert_id": alert_id}


@router.post("/compliance/deletion-approve")
async def compliance_deletion_approve(payload: DeletionApproveIn, user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    approve_user_deletion(user["id"], payload.target_user_id)
    return {"status": "deleted_after_export"}


@router.post("/compliance/apply-retention")
async def compliance_apply_retention(user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return {"status": "success", "deleted": apply_retention_policies()}


@router.get("/admin/review")
async def get_admin_review(limit: int = 100, user: dict = Depends(current_user)):
    _require_workspace_admin(user)
    return admin_review(limit=limit)
