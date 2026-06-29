from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from job_assistant.auth import current_user
from job_assistant.automation_engine import automation_engine
from job_assistant.db import (
    create_automation_rule,
    delete_automation_rule,
    list_automation_errors,
    list_automation_rules,
    list_automation_runs,
    update_automation_rule,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class AutomationRuleIn(BaseModel):
    workspace_id: Optional[int] = None
    name: str
    trigger_event: str = "manual"
    action_type: str = "notify"
    conditions: dict[str, Any] = Field(default_factory=dict)
    action_config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    human_approval_required: bool = True


class AutomationRuleUpdate(BaseModel):
    workspace_id: Optional[int] = None
    name: Optional[str] = None
    trigger_event: Optional[str] = None
    action_type: Optional[str] = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    action_config: dict[str, Any] = Field(default_factory=dict)
    is_active: Optional[bool] = None
    human_approval_required: Optional[bool] = None


class AutomationTriggerIn(BaseModel):
    workspace_id: Optional[int] = None
    trigger_event: str
    payload: dict[str, Any] = Field(default_factory=dict)


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
