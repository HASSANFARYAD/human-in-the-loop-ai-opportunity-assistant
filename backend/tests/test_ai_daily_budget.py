from __future__ import annotations

import pytest
from fastapi import HTTPException

from job_assistant.ai_orchestrator import AIOrchestrator, AIRoute
from job_assistant.config import settings


def _route(provider: str = "openai") -> AIRoute:
    return AIRoute(provider=provider, model="gpt-4o-mini", settings={}, source="test")


def test_no_enforcement_without_user():
    AIOrchestrator()._enforce_daily_budget(None, _route())


def test_fallback_route_is_exempt(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_generation_limit", 1)
    called = False

    def _count(_user_id):
        nonlocal called
        called = True
        return 999

    monkeypatch.setattr("job_assistant.ai_orchestrator.count_ai_generations_today", _count)
    # provider "none" must not even query usage.
    AIOrchestrator()._enforce_daily_budget(1, _route("none"))
    assert called is False


def test_limit_zero_disables_cap(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_generation_limit", 0)
    monkeypatch.setattr("job_assistant.ai_orchestrator.count_ai_generations_today", lambda _u: 10_000)
    AIOrchestrator()._enforce_daily_budget(1, _route())


def test_under_limit_allows(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_generation_limit", 50)
    monkeypatch.setattr("job_assistant.ai_orchestrator.count_ai_generations_today", lambda _u: 49)
    AIOrchestrator()._enforce_daily_budget(1, _route())


def test_at_limit_raises_429(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_generation_limit", 50)
    monkeypatch.setattr("job_assistant.ai_orchestrator.count_ai_generations_today", lambda _u: 50)
    with pytest.raises(HTTPException) as exc:
        AIOrchestrator()._enforce_daily_budget(1, _route())
    assert exc.value.status_code == 429
    assert "Daily AI generation limit" in exc.value.detail
