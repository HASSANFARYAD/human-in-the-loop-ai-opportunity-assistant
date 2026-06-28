from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_assistant.auth import current_user
from job_assistant.config import settings
from job_assistant.db import (
    add_workspace_member,
    create_organization,
    create_workspace,
    enterprise_summary,
    ensure_user_workspace,
    list_permissions,
    list_role_permissions,
    list_roles,
    list_shared_resources,
    list_user_workspaces,
    list_workspace_members,
    share_resource,
    user_has_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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


def _require_workspace_admin(user: dict, workspace_id: int | None = None) -> None:
    workspace = ensure_user_workspace(user["id"])
    scoped_workspace_id = int(workspace_id or workspace.get("workspace_id") or 0)
    role = str(workspace.get("role") or "owner").lower()
    if role in {"owner", "admin"}:
        return
    if scoped_workspace_id and user_has_permission(user["id"], scoped_workspace_id, "workspace:manage"):
        return
    raise HTTPException(status_code=403, detail="Workspace administrator access is required.")


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
