from __future__ import annotations


def test_huggingface_local_provider_routes_without_api_key(monkeypatch):
    from job_assistant.services import ai_providers

    calls: list[tuple[str, str, str]] = []

    def fake_local(model: str, system: str, user: str) -> str:
        calls.append((model, system, user))
        return '{"ok": true, "message": "local"}'

    monkeypatch.setattr(ai_providers, "_huggingface_local", fake_local)

    result = ai_providers.ask_json(
        "system prompt",
        "user prompt",
        {"ok": False, "message": "fallback"},
        provider_settings={
            "api_key": "",
            "config": {
                "provider": "huggingface_local",
                "model": ai_providers.DEFAULT_LOCAL_MODEL,
            },
        },
    )

    assert result["ok"] is True
    assert result["message"] == "local"
    assert calls == [(ai_providers.DEFAULT_LOCAL_MODEL, "system prompt", "user prompt")]
