import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionTaken(str, Enum):
    ALLOW = "ALLOW"
    LOG_ONLY = "LOG_ONLY"
    BLOCK = "BLOCK"


class ThreatType(str, Enum):
    INSTRUCTION_OVERRIDE = "instruction_override"
    ROLE_HIJACKING = "role_hijacking"
    SYSTEM_PROMPT_EXTRACTION = "system_prompt_extraction"
    JAILBREAK = "jailbreak"
    HIDDEN_INSTRUCTION = "hidden_instruction"
    FILE_ACCESS_VIOLATION = "file_access_violation"
    UNAUTHORIZED_OUTBOUND = "unauthorized_outbound"
    SENSITIVE_DATA_MEMORY = "sensitive_data_memory"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    UNKNOWN = "unknown"


class ShieldEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    session_id: Optional[str] = None
    request_method: str
    request_path: str
    response_status: Optional[int] = None
    latency_ms: Optional[int] = None
    llm_provider: Optional[str] = None
    body_snapshot: Optional[str] = None
    threat_type: Optional[str] = None
    risk_score: float = 0.0
    action_taken: str = ActionTaken.ALLOW.value


class ShieldAlert(BaseModel):
    event_id: str
    alert_type: str
    severity: str
    detail: Optional[str] = None


class ScanResult(BaseModel):
    threat_type: Optional[str] = None
    risk_score: float = 0.0
    action: ActionTaken = ActionTaken.ALLOW
    detail: Optional[str] = None


class DashboardStats(BaseModel):
    recent_events: list[dict[str, Any]] = []
    blocked_today: int = 0
    threat_summary: list[dict[str, Any]] = []
    user_call_counts: dict[str, int] = {}
