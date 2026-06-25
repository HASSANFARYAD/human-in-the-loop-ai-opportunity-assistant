from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import HTTPException

from job_assistant.config import settings
from job_assistant.db import (
    count_ai_generations_today,
    get_integration_settings,
    list_provider_configs,
    log_ai_generation,
)
from job_assistant.services.ai_providers import ask_json as ask_json_direct
from job_assistant.services.ai_providers import ask_text as ask_text_direct
from job_assistant.services.ai_providers import ask_text_stream as ask_text_stream_direct
from job_assistant.services.ai_providers import ask_tool_json as ask_tool_json_direct

# Approximate cost per 1K tokens (input, output) in USD for common models.
# Used to populate estimated_cost on AI generation logs.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o-mini-2024-07-18": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-4": (0.03, 0.06),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "o1": (0.015, 0.06),
    "o1-mini": (0.003, 0.012),
    "o3-mini": (0.0011, 0.0044),
    # Anthropic
    "claude-3-opus": (0.015, 0.075),
    "claude-3-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
    "claude-3-5-sonnet": (0.003, 0.015),
    "claude-3-5-haiku": (0.0008, 0.004),
    # Google
    "gemini-1.5-pro": (0.0035, 0.0105),
    "gemini-1.5-flash": (0.000075, 0.0003),
    "gemini-2.0-flash": (0.0001, 0.0004),
    "gemini-2.0-flash-lite": (0.000075, 0.0003),
    # xAI
    "grok-2": (0.002, 0.01),
    "grok-2-latest": (0.002, 0.01),
    "grok-3": (0.003, 0.015),
    # Groq
    "llama-3.3-70b": (0.00059, 0.00079),
    "llama-3.1-8b": (0.00005, 0.00008),
    "mixtral-8x7b": (0.00024, 0.00024),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for an AI generation using the pricing table."""
    model_lower = model.lower().strip()
    prices = _MODEL_PRICING.get(model_lower)
    if prices:
        return round((input_tokens / 1000) * prices[0] + (output_tokens / 1000) * prices[1], 6)
    # Fallback: try prefix match
    for m, (in_price, out_price) in _MODEL_PRICING.items():
        if model_lower.startswith(m):
            return round((input_tokens / 1000) * in_price + (output_tokens / 1000) * out_price, 6)
    # Unknown model — return 0
    return 0.0


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
                if config.get("is_active") is False:
                    return AIRoute("none", "fallback", {"service": "ai_provider", "api_key": "", "config": {}}, "fallback")
                return AIRoute((config.get("provider") or "openai").lower(), config.get("model") or "gpt-4o-mini", legacy, "integration_settings")
        return AIRoute("none", "fallback", {"service": "ai_provider", "api_key": "", "config": {}}, "fallback")

    def _enforce_daily_budget(self, user_id: Optional[int], route: AIRoute) -> None:
        # Only billable provider calls count against the budget; local/fallback
        # routes are free and exempt.
        limit = settings.ai_daily_generation_limit
        if not user_id or limit <= 0 or route.provider in ("", "none"):
            return
        used = count_ai_generations_today(user_id)
        if used >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily AI generation limit ({limit}) reached. It resets at 00:00 UTC.",
            )

    def ask_json(self, system: str, user: str, fallback: Dict[str, Any], *, user_id: Optional[int] = None, task_type: str = "general", prompt_version: str = "", workspace_id: Optional[int] = None) -> Dict[str, Any]:
        route = self.resolve_route(user_id, task_type, workspace_id=workspace_id)
        self._enforce_daily_budget(user_id, route)
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
                cost = _estimate_cost(route.model, input_tokens, output_tokens)
                log_ai_generation(user_id, provider=route.provider, model=route.model, task_type=task_type, prompt_version=prompt_version, prompt_hash=prompt_hash, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost=cost, latency_ms=int((time.perf_counter() - started) * 1000), status=status, error_message=error, workspace_id=workspace_id)

    def ask(self, system: str, user: str, *, user_id: Optional[int] = None, task_type: str = "general", prompt_version: str = "", workspace_id: Optional[int] = None) -> str:
        """Free-form conversational completion. Returns plain assistant text
        (empty string when no provider is configured or the call fails)."""
        route = self.resolve_route(user_id, task_type, workspace_id=workspace_id)
        self._enforce_daily_budget(user_id, route)
        started = time.perf_counter()
        status = "success"
        error = ""
        prompt_hash = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
        input_tokens = len((system + "\n" + user).split())
        output_tokens = 0
        text = ""
        try:
            text = ask_text_direct(system, user, user_id=user_id, provider_settings=route.settings)
            if not text:
                status = "fallback"
            output_tokens = len(text.split())
            return text
        except Exception as exc:
            status = "failed"
            error = str(exc)[:1000]
            return ""
        finally:
            if user_id:
                cost = _estimate_cost(route.model, input_tokens, output_tokens)
                log_ai_generation(user_id, provider=route.provider, model=route.model, task_type=task_type, prompt_version=prompt_version, prompt_hash=prompt_hash, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost=cost, latency_ms=int((time.perf_counter() - started) * 1000), status=status, error_message=error, workspace_id=workspace_id)


    def ask_tool_json(
        self, system: str, user: str, tools: list[dict[str, Any]], fallback: Dict[str, Any],
        *, user_id: Optional[int] = None, task_type: str = "agent_routing", prompt_version: str = "",
        workspace_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        route = self.resolve_route(user_id, task_type, workspace_id=workspace_id)
        self._enforce_daily_budget(user_id, route)
        started = time.perf_counter()
        status = "success"
        error = ""
        prompt_hash = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
        input_tokens = len((system + "\n" + user).split())
        output_tokens = 0
        try:
            data = ask_tool_json_direct(system, user, tools, fallback, user_id=user_id, provider_settings=route.settings)
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
                cost = _estimate_cost(route.model, input_tokens, output_tokens)
                log_ai_generation(user_id, provider=route.provider, model=route.model, task_type=task_type, prompt_version=prompt_version, prompt_hash=prompt_hash, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost=cost, latency_ms=int((time.perf_counter() - started) * 1000), status=status, error_message=error, workspace_id=workspace_id)

    def ask_stream(
        self, system: str, user: str, *, user_id: Optional[int] = None, task_type: str = "general", prompt_version: str = "", workspace_id: Optional[int] = None
    ):
        """Generator that yields tokens from the AI provider as they arrive."""
        route = self.resolve_route(user_id, task_type, workspace_id=workspace_id)
        self._enforce_daily_budget(user_id, route)
        started = time.perf_counter()
        status = "success"
        error = ""
        prompt_hash = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
        input_tokens = len((system + "\n" + user).split())
        output_tokens = 0
        collected: list[str] = []
        try:
            for token in ask_text_stream_direct(system, user, user_id=user_id, provider_settings=route.settings):
                collected.append(token)
                output_tokens += 1
                yield token
            if not collected:
                status = "fallback"
        except Exception as exc:
            status = "failed"
            error = str(exc)[:1000]
        finally:
            if user_id:
                cost = _estimate_cost(route.model, input_tokens, output_tokens)
                log_ai_generation(
                    user_id, provider=route.provider, model=route.model, task_type=task_type,
                    prompt_version=prompt_version, prompt_hash=prompt_hash,
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    estimated_cost=cost,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    status=status, error_message=error, workspace_id=workspace_id,
                )


ai_orchestrator = AIOrchestrator()
