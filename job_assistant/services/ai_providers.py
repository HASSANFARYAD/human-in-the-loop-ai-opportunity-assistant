from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests

from job_assistant.db import get_integration_settings

DEFAULT_PROVIDER = "openai"
SUPPORTED_PROVIDERS = {
    "openai": "OpenAI-compatible",
    "azure_openai": "Azure OpenAI / Foundry",
    "grok": "Grok / xAI",
    "claude": "Anthropic Claude",
    "gemini": "Google Gemini",
    "huggingface": "Hugging Face Inference",
}


def _json_from_text(text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return dict(fallback)
    return dict(fallback)


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _openai_compatible(api_key: str, model: str, system: str, user: str, base_url: str | None = None) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    response = client.chat.completions.create(model=model, messages=_messages(system, user), temperature=0.2)
    return response.choices[0].message.content or ""


def _azure_openai(api_key: str, model: str, system: str, user: str, config: dict[str, Any]) -> str:
    from openai import AzureOpenAI

    endpoint = config.get("endpoint") or os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_version = config.get("api_version") or os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    deployment = config.get("deployment") or model
    client = AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
    response = client.chat.completions.create(model=deployment, messages=_messages(system, user), temperature=0.2)
    return response.choices[0].message.content or ""


def _claude(api_key: str, model: str, system: str, user: str) -> str:
    # Uses Anthropic's HTTP API directly to keep the dependency optional.
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": 1800,
            "temperature": 0.2,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return "\n".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")


def _gemini(api_key: str, model: str, system: str, user: str) -> str:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    response = requests.post(
        endpoint,
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2},
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")


def _huggingface(api_key: str, model: str, system: str, user: str, config: dict[str, Any]) -> str:
    endpoint = config.get("endpoint") or f"https://api-inference.huggingface.co/models/{model}"
    prompt = f"System: {system}\n\nUser: {user}\n\nReturn JSON only."
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"inputs": prompt, "parameters": {"temperature": 0.2, "max_new_tokens": 1600}},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list) and data:
        return data[0].get("generated_text", "")
    if isinstance(data, dict):
        return data.get("generated_text", data.get("summary_text", ""))
    return str(data)


def get_user_ai_settings(user_id: Optional[int]) -> dict[str, Any]:
    if user_id:
        saved = get_integration_settings(user_id, "ai_provider")
        if saved:
            return saved
    return {
        "service": "ai_provider",
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "config": {"provider": DEFAULT_PROVIDER, "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini")},
    }


def ask_json(
    system: str,
    user: str,
    fallback: Dict[str, Any],
    *,
    user_id: Optional[int] = None,
    provider_settings: Optional[dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = provider_settings or get_user_ai_settings(user_id)
    config = settings.get("config", {}) or {}
    provider = (config.get("provider") or DEFAULT_PROVIDER).strip().lower()
    api_key = (settings.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    model = (config.get("model") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    if not api_key:
        return dict(fallback)

    try:
        if provider == "azure_openai":
            text = _azure_openai(api_key, model, system, user, config)
        elif provider == "grok":
            text = _openai_compatible(api_key, model or "grok-3-mini", system, user, config.get("base_url") or "https://api.x.ai/v1")
        elif provider == "claude":
            text = _claude(api_key, model or "claude-3-5-sonnet-latest", system, user)
        elif provider == "gemini":
            text = _gemini(api_key, model or "gemini-1.5-pro", system, user)
        elif provider == "huggingface":
            text = _huggingface(api_key, model, system, user, config)
        else:
            text = _openai_compatible(api_key, model, system, user, config.get("base_url"))
        data = _json_from_text(text, fallback)
        return data or dict(fallback)
    except Exception as exc:
        out = dict(fallback)
        out["_ai_error"] = f"{provider}: {exc}"
        return out
