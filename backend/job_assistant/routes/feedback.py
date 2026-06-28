from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from job_assistant.auth import current_user
from job_assistant.db import (
    create_feedback,
    get_feedback,
    list_audit_logs,
    list_feedback,
    update_feedback_status,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackCreate(BaseModel):
    workspace_id: Optional[int] = None
    category: str = "General Suggestion"
    title: str
    description: str
    severity: str = "medium"
    attachment_url: str = ""
    page_url: str = ""
    user_agent: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class FeedbackStatusUpdate(BaseModel):
    status: str


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
