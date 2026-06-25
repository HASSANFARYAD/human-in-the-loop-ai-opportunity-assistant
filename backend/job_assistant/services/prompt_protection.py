from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── injection patterns ─────────────────────────────────────────────────
# These are matched (case-insensitive) in user-supplied text. When found,
# the *entire sentence or block containing the pattern* is stripped.

_SYSTEM_OVERRIDE_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+all\s+previous\s+(instructions|directives|commands|prompts)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous)\s+(instructions|directives|commands|prompts)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior)\s+(instructions|directives|commands|prompts|context)", re.IGNORECASE),
    re.compile(r"you\s+(are\s+)?now\s+(\w+\s+){0,4}(system|assistant|new|gpt|free|unrestricted|unconstrained)", re.IGNORECASE),
    re.compile(r"(from\s+)?now\s+on\s*,?\s*you\s+are", re.IGNORECASE),
    re.compile(r"new\s+(system\s+)?(prompt|instructions|directives?|commands?)", re.IGNORECASE),
    re.compile(r"system\s*(message|prompt)?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(system|previous|default)\s+(instructions|prompt|directives|commands)", re.IGNORECASE),
    re.compile(r"you\s+(no\s+longer|don.t\s+have\s+to|are\s+not\s+bound\s+by|do\s+not\s+need\s+to\s+follow)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a\s+new|the\s+system|an?\s+unrestricted)", re.IGNORECASE),
    re.compile(r"output\s+(your\s+)?(system\s+)?(prompt|instructions|directives)\b", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions|directives)\b", re.IGNORECASE),
    re.compile(r"print\s+(your\s+)?(system\s+)?(prompt|instructions|directives)\b", re.IGNORECASE),
    re.compile(r"show\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions)\b", re.IGNORECASE),
    re.compile(r"repeat\s+(everything|all|the\s+above|the\s+prompt|your\s+instructions)", re.IGNORECASE),
    re.compile(r"tell\s+me\s+(the|your)\s+(system\s+)?(prompt|instructions)\b", re.IGNORECASE),
    re.compile(r"you\s+are\s+(obligated|required|programmed)\s+to\s+(obey|follow|respond)", re.IGNORECASE),
]

SYSTEM_OVERRIDE_PATTERNS = _SYSTEM_OVERRIDE_PATTERNS  # public alias for testing


def has_injection(text: str) -> bool:
    """Return True if *text* contains any known prompt-injection pattern."""
    if not text:
        return False
    for pat in _SYSTEM_OVERRIDE_PATTERNS:
        if pat.search(text):
            return True
    return False


def sanitize_user_input(text: str, max_length: int = 10000) -> str:
    """Strip or neutralise known injection patterns from user-supplied text.

    1. Truncate to *max_length* characters.
    2. Remove whole lines that match an injection pattern.
    3. Strip leading/trailing whitespace.
    """
    if not text:
        return ""

    text = text[:max_length]

    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        if _line_is_injection(line):
            logger.debug("Stripped injection line: %.120s", line)
            continue
        cleaned.append(line)

    result = "\n".join(cleaned).strip()
    return result


def _line_is_injection(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for pat in _SYSTEM_OVERRIDE_PATTERNS:
        if pat.search(stripped):
            return True
    return False
