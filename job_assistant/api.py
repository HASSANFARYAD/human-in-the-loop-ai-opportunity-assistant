from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from starlette.responses import Response

from job_assistant.auth import authenticate_user, create_access_token, current_user, public_user, register_user
from job_assistant.compliance import admin_review, apply_retention_policies, approve_user_deletion, export_user_data, list_compliance_exports, request_user_deletion
from job_assistant.db import (
    create_feedback,
    create_reminder,
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
    save_evaluation,
    save_integration_settings,
    save_materials,
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
    list_permissions,
    list_role_permissions,
    list_roles,
    list_shared_resources,
    list_user_workspaces,
    list_workspace_members,
    share_resource,
    user_has_permission,
    update_status,
    upsert_profile,
)
from job_assistant.runtime import runtime_status, validate_startup_configuration
from job_assistant.provider_registry import provider_registry
from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.automation_engine import automation_engine
from job_assistant.observability import acknowledge_alert, metrics_summary, prometheus_text
from job_assistant.publishing_engine import approve_post, publish_post, validate_target
from job_assistant.services.apify_integration import apify_items_to_opportunities, build_run_input, run_actor_for_items
from job_assistant.services.generation import generate_materials
from job_assistant.services.parsing import extract_job_from_text, jobs_from_csv
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.rapidapi_linkedin import search_linkedin_jobs, rapidapi_items_to_opportunities
from job_assistant.services.scoring import score_job
from job_assistant.worker_queue import enqueue_job, list_worker_jobs, worker_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


class ProfileCreate(BaseModel):
    cv_text: str
    target_roles: str
    industries: str
    locations: str
    remote_preference: str
    salary_expectations: str
    work_authorization: str
    years_experience: str
    skills: str
    deal_breakers: str


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


class DiscoveryExtractIn(BaseModel):
    workspace_id: Optional[int] = None
    raw: str
    source: str = "Manual"
    opportunity_type: str = "auto"


class DiscoveryPublicIn(BaseModel):
    query: str = ""
    sources: list[str] = Field(default_factory=list)
    limit_per_source: int = 20
    opportunity_type: str = "auto"
    remote_type: str = "all"
    location: str = ""
    keywords: str = ""


class DiscoveryImportIn(BaseModel):
    workspace_id: Optional[int] = None
    opportunities: list[Dict[str, Any]] = Field(default_factory=list)


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


class AIAskIn(BaseModel):
    workspace_id: Optional[int] = None
    system: str = "You are a helpful assistant. Return JSON only."
    prompt: str
    fallback: Dict[str, Any] = Field(default_factory=dict)
    task_type: str = "general"
    prompt_version: str = ""


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
async def health_check_ai(user: dict = Depends(current_user)):
    route = ai_orchestrator.resolve_route(user["id"])
    return {
        "status": "ok",
        "provider": route.provider,
        "model": route.model,
        "source": route.source,
        "configured": bool((route.settings.get("api_key") or "").strip()),
        "timestamp": datetime.utcnow().isoformat(),
    }


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
    return {"status": "success" if acknowledge_alert(alert_id) else "not_found"}


@router.get("/workers/health")
async def get_worker_health(user: dict = Depends(current_user)):
    return worker_health()


@router.get("/workers/jobs")
async def get_worker_jobs(limit: int = 100, status: str = "", user: dict = Depends(current_user)):
    return list_worker_jobs(limit=limit, status=status)


@router.post("/workers/jobs")
async def post_worker_job(payload: WorkerJobIn, user: dict = Depends(current_user)):
    job_id = enqueue_job(payload.job_type, payload.payload, queue_name=payload.queue_name, run_after=payload.run_after)
    return {"id": job_id, "status": "queued"}


@router.post("/auth/register")
async def register(user_data: UserRegister):
    if len(user_data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    try:
        user = register_user(user_data.email, user_data.password, user_data.full_name)
        token = create_access_token(user)
        return {"access_token": token, "token_type": "bearer", "user": public_user(user)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail="Failed to register user")


@router.post("/auth/login")
async def login(login_data: UserLogin):
    user = authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


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


@router.get("/jobs")
async def list_all_jobs(workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        jobs = list_jobs(user["id"], workspace_id=workspace_id)
        return jobs
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list jobs")


@router.post("/jobs")
async def create_job(job_data: JobCreate, user: dict = Depends(current_user)):
    try:
        job_id = insert_job(job_data.dict(), user["id"], workspace_id=job_data.workspace_id)
        return {"id": job_id, "status": "success", "message": "Job created"}
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job")


def _filter_discovered_opportunities(items: list[dict[str, Any]], payload: DiscoveryPublicIn) -> list[dict[str, Any]]:
    keywords = " ".join(part for part in [payload.query, payload.keywords] if part).strip().lower()
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


@router.post("/discovery/extract")
async def discovery_extract(payload: DiscoveryExtractIn, user: dict = Depends(current_user)):
    try:
        opportunity = extract_job_from_text(payload.raw, source=payload.source, opportunity_type=payload.opportunity_type, user_id=user["id"])
        return {"status": "success", "opportunity": opportunity}
    except Exception as e:
        logger.error(f"Error extracting opportunity: {e}")
        raise HTTPException(status_code=500, detail="Failed to extract opportunity")


@router.post("/discovery/public")
async def discovery_public(payload: DiscoveryPublicIn, user: dict = Depends(current_user)):
    try:
        sources = payload.sources or ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"]
        opportunities = discover_public_opportunities(payload.query, sources, payload.limit_per_source)
        return {"status": "success", "opportunities": _filter_discovered_opportunities(opportunities, payload)}
    except Exception as e:
        logger.error(f"Error discovering public opportunities: {e}")
        raise HTTPException(status_code=502, detail=f"Public discovery failed: {e}")


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
        return {"status": "success", "opportunities": rapidapi_items_to_opportunities(items), "raw_count": len(items)}
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
        opportunities = apify_items_to_opportunities(items, source=f"Apify:{actor_id}")
        return {"status": "success", "opportunities": opportunities, "raw_count": len(items)}
    except Exception as e:
        logger.error(f"Error running Apify discovery: {e}")
        raise HTTPException(status_code=502, detail=f"Apify scraper failed: {e}")


@router.post("/discovery/import")
async def discovery_import(payload: DiscoveryImportIn, user: dict = Depends(current_user)):
    ids: list[int] = []
    for item in payload.opportunities:
        try:
            ids.append(insert_job(item, user["id"], workspace_id=payload.workspace_id))
        except Exception as e:
            logger.error(f"Error importing discovered opportunity: {e}")
            raise HTTPException(status_code=500, detail="Failed to import discovered opportunities")
    return {"status": "success", "ids": ids, "count": len(ids)}


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
        delete_job(job_id, user["id"], workspace_id=workspace_id)
        return {"status": "success", "message": "Opportunity deleted"}
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete job")


@router.post("/jobs/{job_id}/score")
async def score_single_job(job_id: int, user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"])
        if not profile:
            raise HTTPException(status_code=400, detail="Profile not configured")

        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        evaluation = score_job(profile, job, user_id=user["id"])
        save_evaluation(job_id, evaluation, user["id"])
        return evaluation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scoring job: {e}")
        raise HTTPException(status_code=500, detail="Failed to score job")


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

        materials = generate_materials(profile, job, evaluation, user_id=user["id"])
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
    approve_user_deletion(user["id"], payload.target_user_id)
    return {"status": "deleted_after_export"}


@router.post("/compliance/apply-retention")
async def compliance_apply_retention(user: dict = Depends(current_user)):
    return {"status": "success", "deleted": apply_retention_policies()}


@router.get("/admin/review")
async def get_admin_review(limit: int = 100, user: dict = Depends(current_user)):
    return admin_review(limit=limit)
