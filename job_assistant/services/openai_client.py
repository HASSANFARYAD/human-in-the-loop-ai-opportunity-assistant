from __future__ import annotations

from typing import Any, Dict, Optional

from .ai_providers import ask_json as ask_json_multi_provider


def has_openai() -> bool:
    # Backward-compatible helper. Multi-provider generation now checks the
    # selected user's provider settings inside ask_json_multi_provider.
    import os

    return bool(os.getenv("OPENAI_API_KEY"))


def ask_json(system: str, user: str, fallback: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
    return ask_json_multi_provider(system, user, fallback, user_id=user_id)
