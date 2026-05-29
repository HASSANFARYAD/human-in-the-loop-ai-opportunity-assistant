from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from job_assistant.db import get_integration_settings, list_provider_configs, log_ai_generation
from job_assistant.services.ai_providers import ask_json as ask_json_direct


@dataclass
class AIRoute:
    provider: str
    model: str
    settings: dict[str, Any]
    source: str = "integration_settings"


class AIOrchestrator:
    def resolve_route(self, user_id: Optional[int], task_type: str = "general", workspace_id: Optional[int] = None) -> AIRoute:
        if user_id:
            configured = list_provider_configs(user_id, platform="ai", include_credentials=True, workspace_id=workspace_id)
            for item in configured:
                if not item.get("is_active"):
                    continue
                credentials = item.get("credentials") or {}
                config = item.get("config") or {}
                secret = credentials.get("api_key") or credentials.get("token") or credentials.get("access_token")
                if secret:
                    provider = (config.get("provider") or item.get("provider_name") or "openai").lower()
                    model = config.get("model") or "gpt-4o-mini"
                    return AIRoute(provider, model, {"service": "ai_provider", "api_key": secret, "config": {**config, "provider": provider, "model": model}}, "provider_configs")
            legacy = get_integration_settings(user_id, "ai_provider", workspace_id=workspace_id)
            if legacy:
                config = legacy.get("config") or {}
                return AIRoute((config.get("provider") or "openai").lower(), config.get("model") or "gpt-4o-mini", legacy, "integration_settings")
        return AIRoute("none", "fallback", {"service": "ai_provider", "api_key": "", "config": {}}, "fallback")

    def ask_json(self, system: str, user: str, fallback: Dict[str, Any], *, user_id: Optional[int] = None, task_type: str = "general", prompt_version: str = "", workspace_id: Optional[int] = None) -> Dict[str, Any]:
        route = self.resolve_route(user_id, task_type, workspace_id=workspace_id)
        started = time.perf_counter()
        status = "success"
        error = ""
        prompt_hash = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
        input_tokens = len((system + "\n" + user).split())
        output_tokens = 0
        try:
            data = ask_json_direct(system, user, fallback, user_id=user_id, provider_settings=route.settings)
            if isinstance(data, dict) and data.get("_ai_error"):
                status = "fallback"
                error = str(data.get("_ai_error"))[:1000]
            output_tokens = len(str(data).split())
            return data or dict(fallback)
        except Exception as exc:
            status = "failed"
            error = str(exc)[:1000]
            return dict(fallback)
        finally:
            if user_id:
                log_ai_generation(user_id, provider=route.provider, model=route.model, task_type=task_type, prompt_version=prompt_version, prompt_hash=prompt_hash, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.perf_counter() - started) * 1000), status=status, error_message=error, workspace_id=workspace_id)


ai_orchestrator = AIOrchestrator()
