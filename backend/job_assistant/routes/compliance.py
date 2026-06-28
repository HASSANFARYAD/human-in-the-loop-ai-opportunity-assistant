from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_assistant.auth import current_user
from job_assistant.compliance import (
    admin_review,
    apply_retention_policies,
    approve_user_deletion,
    export_user_data,
    list_compliance_exports,
    request_user_deletion,
)
from job_assistant.db import delete_user_data

logger = logging.getLogger(__name__)

router = APIRouter()


class DeletionRequestIn(BaseModel):
    reason: str = ""


class DeletionApproveIn(BaseModel):
    target_user_id: int


def _require_workspace_admin(user: dict, workspace_id: int | None = None) -> None:
    from job_assistant.db import ensure_user_workspace, user_has_permission
    workspace = ensure_user_workspace(user["id"])
    scoped_workspace_id = int(workspace_id or workspace.get("workspace_id") or 0)
    role = str(workspace.get("role") or "owner").lower()
    if role in {"owner", "admin"}:
        return
    if scoped_workspace_id and user_has_permission(user["id"], scoped_workspace_id, "workspace:manage"):
        return
    raise HTTPException(status_code=403, detail="Workspace administrator access is required.")


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
