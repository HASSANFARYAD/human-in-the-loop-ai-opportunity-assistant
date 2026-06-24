from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, Optional

import requests

from job_assistant.db import get_integration_settings

DEFAULT_PROVIDER = "huggingface_local"
SUPPORTED_PROVIDERS = {
    "openai": "OpenAI-compatible",
    "huggingface_local": "Hugging Face Local (Transformers)",
    "langchain_openai": "LangChain + OpenAI-compatible",
    "azure_openai": "Azure OpenAI / Foundry",
    "grok": "Grok / xAI",
    "claude": "Anthropic Claude",
    "gemini": "Google Gemini",
    "huggingface": "Hugging Face Inference",
}

DEFAULT_LOCAL_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


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


def _is_local_ollama_base_url(base_url: str | None) -> bool:
    normalized = (base_url or "").strip().rstrip("/")
    return normalized.startswith("http://localhost:11434") or normalized.startswith("http://127.0.0.1:11434") or normalized.startswith("http://[::1]:11434")


def _openai_compatible(api_key: str, model: str, system: str, user: str, base_url: str | None = None) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url or None)
    response = client.chat.completions.create(model=model, messages=_messages(system, user), temperature=0.2, max_tokens=4096)
    return response.choices[0].message.content or ""


def _langchain_openai(api_key: str, model: str, system: str, user: str, config: dict[str, Any]) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    base_url = (config.get("base_url") or "").strip() or None
    resolved_api_key = api_key or ("ollama" if _is_local_ollama_base_url(base_url) else "")
    if not resolved_api_key:
        raise ValueError("Missing API key for LangChain OpenAI-compatible provider")

    client = ChatOpenAI(api_key=resolved_api_key, base_url=base_url, model=model, temperature=0.2, max_tokens=4096)
    response = client.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = getattr(response, "content", "")
    if isinstance(content, list):
        pieces: list[str] = []
        for part in content:
            if isinstance(part, dict):
                pieces.append(str(part.get("text") or part.get("content") or ""))
            else:
                pieces.append(str(part))
        return "\n".join(piece for piece in pieces if piece)
    return str(content or "")


@lru_cache(maxsize=4)
def _load_local_hf_model(model_id: str):
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Install transformers and torch to use Hugging Face local mode.") from exc

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=False)
    model_kwargs: dict[str, Any] = {"trust_remote_code": False}
    if torch.cuda.is_available():
        model_kwargs["torch_dtype"] = torch.float16
    else:
        model_kwargs["torch_dtype"] = torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs)
    return tokenizer, model


def _huggingface_local(model: str, system: str, user: str) -> str:
    import torch

    model_id = model or DEFAULT_LOCAL_MODEL
    tokenizer, loaded_model = _load_local_hf_model(model_id)
    messages = _messages(system, user)
    try:
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        prompt = f"System: {system}\n\nUser: {user}\n\nAssistant:"
    inputs = tokenizer(prompt, return_tensors="pt")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    loaded_model = loaded_model.to(device)
    with torch.no_grad():
        output_ids = loaded_model.generate(
            **inputs,
            max_new_tokens=4096,
            do_sample=False,
            temperature=0.2,
            pad_token_id=tokenizer.eos_token_id or tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    generated = output_ids[0][inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def _azure_openai(api_key: str, model: str, system: str, user: str, config: dict[str, Any]) -> str:
    from openai import AzureOpenAI

    endpoint = config.get("endpoint") or ""
    api_version = config.get("api_version") or "2024-10-21"
    deployment = config.get("deployment") or model
    # Reasoning/codex deployments (e.g. gpt-5.x, o-series, *-codex) only expose the
    # Responses API; classic chat models use Chat Completions. "auto" picks based on
    # the deployment name, or set api_style explicitly to "responses"/"chat".
    api_style = (config.get("api_style") or "auto").strip().lower()
    if api_style == "auto":
        name = (deployment or model or "").lower()
        api_style = "responses" if any(tag in name for tag in ("codex", "gpt-5", "o1", "o3", "o4")) else "chat"
    client = AzureOpenAI(api_key=api_key, azure_endpoint=endpoint, api_version=api_version)
    if api_style == "responses":
        response = client.responses.create(model=deployment, instructions=system, input=user, max_output_tokens=4096)
        return response.output_text or ""
    response = client.chat.completions.create(model=deployment, messages=_messages(system, user), temperature=0.2, max_tokens=4096)
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
            "max_tokens": 4096,
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
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
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
        json={"inputs": prompt, "parameters": {"temperature": 0.2, "max_new_tokens": 4096}},
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
    """Load the signed-in user's AI provider settings from the database only."""
    if user_id:
        saved = get_integration_settings(user_id, "ai_provider")
        if saved:
            return saved
    return {
        "service": "ai_provider",
        "api_key": "",
        "config": {"provider": "huggingface_local", "model": DEFAULT_LOCAL_MODEL},
    }


def _generate_text(system: str, user: str, settings: dict[str, Any]) -> str:
    """Dispatch a single (system, user) turn to the configured provider and
    return its raw text. Raises on provider/transport errors and on a missing
    API key for providers that require one."""
    config = settings.get("config", {}) or {}
    provider = (config.get("provider") or DEFAULT_PROVIDER).strip().lower()
    api_key = (settings.get("api_key") or "").strip()
    model = (config.get("model") or "gpt-4o-mini").strip()
    base_url = config.get("base_url") or ""
    if provider in {"huggingface_local"}:
        api_key = ""
    elif provider != "langchain_openai" and not api_key:
        raise ValueError(f"Missing API key for provider '{provider}'")
    if provider == "langchain_openai" and not api_key and not _is_local_ollama_base_url(base_url):
        raise ValueError("Missing API key for LangChain OpenAI-compatible provider")

    if provider == "huggingface_local":
        return _huggingface_local(model or DEFAULT_LOCAL_MODEL, system, user)
    if provider == "langchain_openai":
        return _langchain_openai(api_key, model or "llama3.1", system, user, config)
    if provider == "azure_openai":
        return _azure_openai(api_key, model, system, user, config)
    if provider == "grok":
        return _openai_compatible(api_key, model or "grok-3-mini", system, user, config.get("base_url") or "https://api.x.ai/v1")
    if provider == "claude":
        return _claude(api_key, model or "claude-3-5-sonnet-latest", system, user)
    if provider == "gemini":
        return _gemini(api_key, model or "gemini-1.5-pro", system, user)
    if provider == "huggingface":
        return _huggingface(api_key, model, system, user, config)
    return _openai_compatible(api_key, model, system, user, config.get("base_url"))


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
    api_key = (settings.get("api_key") or "").strip()
    base_url = config.get("base_url") or ""
    if provider not in {"huggingface_local"} and provider != "langchain_openai" and not api_key:
        return dict(fallback)
    if provider == "langchain_openai" and not api_key and not _is_local_ollama_base_url(base_url):
        return dict(fallback)

    try:
        text = _generate_text(system, user, settings)
        data = _json_from_text(text, fallback)
        return data or dict(fallback)
    except Exception as exc:
        out = dict(fallback)
        out["_ai_error"] = f"{provider}: {exc}"
        return out


def ask_text(
    system: str,
    user: str,
    *,
    user_id: Optional[int] = None,
    provider_settings: Optional[dict[str, Any]] = None,
) -> str:
    """Free-form conversational completion. Returns plain assistant text, or an
    empty string when no provider is configured or the call fails (callers
    supply their own user-facing fallback copy)."""
    settings = provider_settings or get_user_ai_settings(user_id)
    config = settings.get("config", {}) or {}
    provider = (config.get("provider") or DEFAULT_PROVIDER).strip().lower()
    api_key = (settings.get("api_key") or "").strip()
    base_url = config.get("base_url") or ""
    if provider not in {"huggingface_local"} and provider != "langchain_openai" and not api_key:
        return ""
    if provider == "langchain_openai" and not api_key and not _is_local_ollama_base_url(base_url):
        return ""

    try:
        return (_generate_text(system, user, settings) or "").strip()
    except Exception:
        return ""
