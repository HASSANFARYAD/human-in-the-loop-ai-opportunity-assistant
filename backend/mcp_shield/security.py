import re
from typing import Any

from mcp_shield.events import ActionTaken, ScanResult, ThreatType


_INSTRUCTION_OVERRIDE_PATTERNS: list[tuple[str, float]] = [
    (r"\bignore\s+(all\s+)?(previous|above|prior)\s+instructions\b", 70),
    (r"\bdisregard\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|directives)\b", 70),
    (r"\bdo\s+not\s+follow\s+(the\s+)?(above|previous)\s+instructions\b", 65),
    (r"\bdo\s+not\s+adhere\s+to\b", 60),
]

_ROLE_HIJACKING_PATTERNS: list[tuple[str, float]] = [
    (r"\byou\s+are\s+now\b", 75),
    (r"\bact\s+as\s+if\s+you\s+are\b", 70),
    (r"\bpretend\s+(to\s+be|you\s+are)\b", 65),
    (r"\bfrom\s+now\s+on\s+you\s+are\b", 75),
    (r"\byou\s+are\s+(now\s+)?a\s+(new|different)\b", 70),
    (r"\boverride\s+(your\s+)?(system\s+)?(prompt|role|persona)\b", 80),
]

_SYSTEM_PROMPT_EXTRACTION_PATTERNS: list[tuple[str, float]] = [
    (r"\boutput\s+(your\s+)?(system\s+)?prompt\b", 85),
    (r"\bprint\s+(your\s+)?(system\s+)?(prompt|instructions|directives)\b", 85),
    (r"\breveal\s+(your\s+)?(system\s+)?(prompt|instructions|directives)\b", 90),
    (r"\bshow\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions)\b", 80),
    (r"\bwhat\s+(are|is)\s+(your\s+)?(system\s+)?(prompt|instructions)\b", 75),
    (r"\bhow\s+(are\s+)?you\s+(being\s+)?(instructed|programmed|prompted)\b", 70),
    (r"\btell\s+me\s+(your\s+)?(system\s+)?(prompt|instructions)\b", 80),
]

_JAILBREAK_PATTERNS: list[tuple[str, float]] = [
    (r"\bDAN\b", 85),
    (r"\bdo\s+anything\s+now\b", 75),
    (r"\bno\s+(restrictions|limits|boundaries|constraints|rules)\b", 70),
    (r"\byou\s+(don\'t|do\s+not)\s+have\s+(to\s+)?(follow|obey)\b", 75),
    (r"\bunfiltered\b", 65),
    (r"\buncensored\b", 65),
    (r"\bbypass\s+(all\s+)?(restrictions|safety|filters|guardrails)\b", 85),
    (r"\bjailbreak\b", 90),
    (r"\bevil\s+(mode|personality)\b", 80),
]

_HIDDEN_INSTRUCTION_PATTERNS: list[tuple[str, float]] = [
    (r"\bignore\s+(all\s+)?previous\s+(instructions|text|content|directions)\b", 70),
    (r"\bnow\s+you\s+must\b", 50),
    (r"\byour\s+(new|real)\s+(task|goal|mission|purpose)\s+is\b", 65),
    (r"\bwhen\s+you\s+read\s+this\b", 60),
    (r"\bif\s+you\s+(see|find|encounter)\s+(the\s+)?(word|phrase|text)\b", 55),
]

_THREAT_CHECKLIST: list[tuple[list[tuple[str, float]], str]] = [
    (_INSTRUCTION_OVERRIDE_PATTERNS, ThreatType.INSTRUCTION_OVERRIDE.value),
    (_ROLE_HIJACKING_PATTERNS, ThreatType.ROLE_HIJACKING.value),
    (_SYSTEM_PROMPT_EXTRACTION_PATTERNS, ThreatType.SYSTEM_PROMPT_EXTRACTION.value),
    (_JAILBREAK_PATTERNS, ThreatType.JAILBREAK.value),
    (_HIDDEN_INSTRUCTION_PATTERNS, ThreatType.HIDDEN_INSTRUCTION.value),
]


def _flatten_text(body: dict[str, Any]) -> str:
    texts: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            texts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(body)
    return " ".join(texts).lower()


def scan_for_injection(body: dict[str, Any], path: str = "") -> ScanResult:
    text = _flatten_text(body)
    if not text.strip():
        return ScanResult()

    max_risk: float = 0.0
    detected_threat: str | None = None

    for patterns, threat_type in _THREAT_CHECKLIST:
        for pattern, base_risk in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if base_risk > max_risk:
                    max_risk = base_risk
                    detected_threat = threat_type

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
        detail=f"Matched threat pattern: {detected_threat}" if detected_threat else None,
    )
