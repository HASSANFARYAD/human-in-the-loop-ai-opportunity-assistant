import json
import re
from typing import Any, Optional

from mcp_shield.events import ActionTaken, ScanResult, ThreatType
from mcp_shield.database import get_user_call_count


_SENSITIVE_PATTERNS: list[tuple[str, str, float]] = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN", 90),
    (r"\b\d{9}\b", "SSN_RAW", 80),
    (r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b", "CREDIT_CARD", 95),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "EMAIL", 30),
    (r"(?:password|passwd|pwd)\s*[:=]\s*\S+", "PASSWORD", 95),
    (r"(?:api[_-]?key|apikey)\s*[:=]\s*\S+", "API_KEY", 90),
    (r"(?:secret|token)\s*[:=]\s*\S+", "SECRET", 85),
    (r"\b\d{3}-\d{3}-\d{4}\b", "PHONE", 20),
]


_FILE_ACCESS_PATTERNS: list[tuple[str, float]] = [
    (r"(?:read|open|access|list|get)\s+(?:file|files|directory|dir)\s+(?:/|\.\.?)", 85),
    (r"open\s*\([\"']\s*[/~]", 90),
    (r"path\s*[:=]\s*[\"']\s*[/~]", 80),
    (r"(?:os\.|pathlib\.|shutil\.|glob\.)", 70),
    (r"(?:\.\./|\.\.\\)", 85),
    (r"\b/etc/passwd\b", 95),
    (r"\b/var/log\b", 80),
    (r"\b~/\b", 60),
]


_OUTBOUND_URL_PATTERNS: list[tuple[str, float]] = [
    (r"(?:https?://|www\.)\S+", 50),
    (r"(?:requests|httpx|aiohttp|urllib)\.(?:get|post|put|delete|request)", 75),
    (r"(?:fetch|axios)\([\"'\s]*https?://", 75),
]


async def check_rules(
    body: dict[str, Any],
    session_id: Optional[str],
    path: str,
) -> ScanResult:
    text = json.dumps(body).lower() if body else ""
    max_risk: float = 0.0
    detected_threat: str | None = None
    detail: str | None = None

    for pattern, risk in _FILE_ACCESS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if risk > max_risk:
                max_risk = risk
                detected_threat = ThreatType.FILE_ACCESS_VIOLATION.value
                detail = "Agent attempted file access outside permitted directory"

    for pattern, risk in _OUTBOUND_URL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            _check = _check_approved_domains(text)
            if _check:
                if _check > max_risk:
                    max_risk = _check
                    detected_threat = ThreatType.UNAUTHORIZED_OUTBOUND.value
                    detail = "Agent attempted outbound request to non-approved domain"

    if "agent_memory" in path or "memory" in path:
        for pattern, label, risk in _SENSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                if risk > max_risk:
                    max_risk = risk
                    detected_threat = ThreatType.SENSITIVE_DATA_MEMORY.value
                    detail = f"Sensitive data pattern detected in memory write: {label}"

    if session_id and ("ai" in path or "agent" in path or "chat" in path):
        count = await get_user_call_count(session_id)
        if count > settings.max_ai_calls_per_user_per_hour:
            max_risk = 80.0
            detected_threat = ThreatType.RATE_LIMIT_EXCEEDED.value
            detail = f"User exceeded {settings.max_ai_calls_per_user_per_hour} AI calls/hour"

    if max_risk >= 61:
        action = ActionTaken.BLOCK
    elif max_risk >= 31:
        action = ActionTaken.LOG_ONLY
    else:
        action = ActionTaken.ALLOW

    return ScanResult(
        threat_type=detected_threat,
        risk_score=max_risk,
        action=action,
        detail=detail,
    )


def _check_approved_domains(text: str) -> float:
    url_pattern = re.compile(r"https?://([^/\s]+)")
    found_domains = url_pattern.findall(text)
    for domain in found_domains:
        allowed = any(
            approved in domain for approved in settings.approved_outbound_domains
        )
        if not allowed:
            return 70.0
    return 0.0
