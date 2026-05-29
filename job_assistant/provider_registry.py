from __future__ import annotations

"""Provider abstraction layer for user-owned integrations.

This module is intentionally lightweight for the SQLite MVP. It gives the app a
single registry interface for configured providers, health checks, priority
ordering, and fallback execution without forcing every integration to be
rewritten at once.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from job_assistant.db import (
    get_provider_config,
    list_provider_configs,
    record_provider_health,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ProviderExecutionResult:
    provider_name: str
    platform: str
    ok: bool
    result: Any = None
    error: str = ""


class BaseProvider:
    """Base interface all provider adapters should implement."""

    provider_name = "base"
    platform = "generic"
    supported_actions: set[str] = set()

    def __init__(self, *, credentials: dict[str, Any] | None = None, config: dict[str, Any] | None = None):
        self.credentials = credentials or {}
        self.config = config or {}

    def authenticate(self) -> bool:
        """Return True if required credentials appear to be available."""
        return bool(self.credentials.get("api_key") or self.credentials.get("access_token") or self.credentials.get("token"))

    def validate_credentials(self) -> tuple[bool, str]:
        if self.authenticate():
            return True, "credentials_present"
        return False, "missing_credentials"

    def health_check(self) -> dict[str, Any]:
        ok, message = self.validate_credentials()
        return {
            "provider_name": self.provider_name,
            "platform": self.platform,
            "status": "healthy" if ok else "missing_credentials",
            "message": message,
            "checked_at": _utc_now(),
        }

    def execute(self, action: str, payload: dict[str, Any]) -> Any:
        raise NotImplementedError(f"{self.provider_name} does not implement {action}")


class ConfiguredProvider(BaseProvider):
    """Generic adapter for configured providers before platform-specific code exists."""

    provider_name = "configured"
    platform = "generic"

    def __init__(self, *, provider_name: str, platform: str, credentials: dict[str, Any] | None = None, config: dict[str, Any] | None = None):
        super().__init__(credentials=credentials, config=config)
        self.provider_name = provider_name
        self.platform = platform
        actions = config.get("supported_actions") if isinstance(config, dict) else None
        self.supported_actions = set(actions or [])

    def execute(self, action: str, payload: dict[str, Any]) -> Any:
        if self.supported_actions and action not in self.supported_actions:
            raise ValueError(f"Action '{action}' is not enabled for provider '{self.provider_name}'.")
        # The MVP registry validates routing/fallback. Real network execution stays in
        # existing integration modules until platform adapters are added incrementally.
        return {
            "status": "routed",
            "platform": self.platform,
            "provider_name": self.provider_name,
            "action": action,
            "payload_keys": sorted(payload.keys()),
        }


class ProviderRegistry:
    def __init__(self):
        self._adapters: dict[tuple[str, str], type[BaseProvider]] = {}

    def register(self, platform: str, provider_name: str, adapter_cls: type[BaseProvider]) -> None:
        self._adapters[(platform.lower(), provider_name.lower())] = adapter_cls

    def adapter_for(self, platform: str, provider_name: str, *, credentials: dict[str, Any], config: dict[str, Any]) -> BaseProvider:
        adapter_cls = self._adapters.get((platform.lower(), provider_name.lower()))
        if adapter_cls:
            return adapter_cls(credentials=credentials, config=config)
        return ConfiguredProvider(provider_name=provider_name, platform=platform, credentials=credentials, config=config)

    def configured(self, user_id: int, platform: str | None = None, workspace_id: int | None = None) -> list[dict[str, Any]]:
        return list_provider_configs(user_id, platform=platform, include_credentials=False, workspace_id=workspace_id)

    def ordered(self, user_id: int, platform: str, workspace_id: int | None = None) -> list[dict[str, Any]]:
        providers = list_provider_configs(user_id, platform=platform, include_credentials=True, workspace_id=workspace_id)
        return sorted(
            [p for p in providers if p.get("is_active")],
            key=lambda p: (int(p.get("priority") or 100), p.get("provider_name") or ""),
        )

    def health(self, user_id: int, platform: str | None = None, workspace_id: int | None = None) -> list[dict[str, Any]]:
        providers = list_provider_configs(user_id, platform=platform, include_credentials=True, workspace_id=workspace_id)
        results: list[dict[str, Any]] = []
        for provider in providers:
            adapter = self.adapter_for(
                provider["platform"],
                provider["provider_name"],
                credentials=provider.get("credentials", {}),
                config=provider.get("config", {}),
            )
            result = adapter.health_check()
            record_provider_health(
                user_id,
                provider["platform"],
                provider["provider_name"],
                result["status"],
                latency_ms=None,
                error_message="" if result["status"] == "healthy" else result.get("message", ""),
                workspace_id=workspace_id,
            )
            result.update(
                {
                    "priority": provider.get("priority"),
                    "is_active": provider.get("is_active"),
                    "health_status": result["status"],
                }
            )
            results.append(result)
        return results

    def execute_with_fallback(self, user_id: int, platform: str, action: str, payload: dict[str, Any], workspace_id: int | None = None) -> ProviderExecutionResult:
        providers = self.ordered(user_id, platform, workspace_id=workspace_id)
        if not providers:
            return ProviderExecutionResult(provider_name="", platform=platform, ok=False, error="No active providers configured for this platform.")

        last_error = ""
        for provider in providers:
            adapter = self.adapter_for(
                provider["platform"],
                provider["provider_name"],
                credentials=provider.get("credentials", {}),
                config=provider.get("config", {}),
            )
            ok, message = adapter.validate_credentials()
            if not ok:
                last_error = message
                record_provider_health(user_id, platform, provider["provider_name"], "missing_credentials", error_message=message, workspace_id=workspace_id)
                continue
            try:
                result = adapter.execute(action, payload)
                record_provider_health(user_id, platform, provider["provider_name"], "healthy", workspace_id=workspace_id)
                return ProviderExecutionResult(provider_name=provider["provider_name"], platform=platform, ok=True, result=result)
            except Exception as exc:
                last_error = str(exc)
                record_provider_health(user_id, platform, provider["provider_name"], "failed", error_message=last_error, workspace_id=workspace_id)
        return ProviderExecutionResult(provider_name="", platform=platform, ok=False, error=last_error or "All providers failed.")


provider_registry = ProviderRegistry()
