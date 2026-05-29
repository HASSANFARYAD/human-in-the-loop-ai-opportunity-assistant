from __future__ import annotations

from typing import Any, Dict, Optional

from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.db import has_integration_api_key


def has_openai(user_id: Optional[int] = None) -> bool:
    return bool(user_id and has_integration_api_key(user_id, "ai_provider"))


def ask_json(system: str, user: str, fallback: Dict[str, Any], user_id: Optional[int] = None, task_type: str = "general", prompt_version: str = "") -> Dict[str, Any]:
    return ai_orchestrator.ask_json(system, user, fallback, user_id=user_id, task_type=task_type, prompt_version=prompt_version)
