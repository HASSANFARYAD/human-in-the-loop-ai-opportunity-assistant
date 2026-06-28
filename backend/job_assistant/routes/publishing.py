from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from job_assistant.auth import current_user
from job_assistant.db import create_post, list_posts
from job_assistant.publishing_engine import approve_post, publish_post, validate_target

logger = logging.getLogger(__name__)

router = APIRouter()


class PostCreate(BaseModel):
    workspace_id: Optional[int] = None
    title: str = ""
    base_content: str
    status: str = "draft"
    scheduled_at: Optional[str] = None
    targets: list[dict[str, Any]] = Field(default_factory=list)


class PublishRequest(BaseModel):
    dry_run: Optional[bool] = None


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
