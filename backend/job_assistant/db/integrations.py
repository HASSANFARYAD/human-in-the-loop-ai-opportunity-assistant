from __future__ import annotations

import json
from typing import Any, Dict

import pymongo
from pymongo import errors as pymongo_errors

from job_assistant.crypto import decrypt_text, encrypt_text
from job_assistant.db.core import (
    _next_id, _safe_json_loads, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
)

__all__ = [
    "save_integration_settings", "get_integration_settings",
    "delete_integration_settings", "has_integration_api_key",
    "list_integration_settings",
    "save_provider_config", "_provider_row_to_dict",
    "get_provider_config", "list_provider_configs",
    "delete_provider_config", "record_provider_health",
    "save_gmail_messages", "list_gmail_messages",
]


def save_integration_settings(
    user_id: int, service: str, api_key: str = "",
    config: Dict[str, Any] | None = None, *,
    keep_existing_api_key_if_blank: bool = False, workspace_id: int | None = None,
) -> None:
    encrypted_config = encrypt_text(json.dumps(config or {}))
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    col = get_collection("integration_settings")
    existing = col.find_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "service": service})
    if keep_existing_api_key_if_blank and not (api_key or "").strip() and existing:
        encrypted_key = existing.get("api_key") or ""
    else:
        encrypted_key = encrypt_text(api_key or "")
    col.update_one(
        {"user_id": user_id, "workspace_id": scoped_workspace_id, "service": service},
        {"$set": {
            "organization_id": organization_id, "api_key": encrypted_key,
            "config_json": encrypted_config, "updated_at": utc_now(),
        }},
        upsert=True,
    )
    add_audit_log(user_id, "integration.upsert", "integration", service, {"has_api_key": bool((api_key or "").strip())}, workspace_id=scoped_workspace_id, organization_id=organization_id)


def get_integration_settings(user_id: int, service: str, workspace_id: int | None = None) -> dict[str, Any]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    doc = get_collection("integration_settings").find_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "service": service})
    if not doc:
        return {}
    settings = _strip_id(doc)
    settings["api_key"] = decrypt_text(settings.get("api_key") or "")
    try:
        settings["config"] = json.loads(decrypt_text(settings.get("config_json") or "{}") or "{}")
    except json.JSONDecodeError:
        settings["config"] = {}
    return settings


def delete_integration_settings(user_id: int, service: str, workspace_id: int | None = None) -> None:
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    get_collection("integration_settings").delete_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "service": service})
    add_audit_log(user_id, "integration.delete", "integration", service, {}, workspace_id=scoped_workspace_id, organization_id=organization_id)


def has_integration_api_key(user_id: int, service: str, workspace_id: int | None = None) -> bool:
    settings = get_integration_settings(user_id, service, workspace_id=workspace_id)
    return bool((settings.get("api_key") or "").strip())


def list_integration_settings(user_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("integration_settings").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("service", pymongo.ASCENDING)
    integrations: list[dict[str, Any]] = []
    for doc in docs:
        config: dict[str, Any] = {}
        try:
            config = json.loads(decrypt_text(doc.get("config_json") or "{}") or "{}")
        except json.JSONDecodeError:
            config = {}
        integrations.append({
            "service": doc["service"],
            "workspace_id": doc.get("workspace_id"),
            "organization_id": doc.get("organization_id"),
            "has_api_key": bool(decrypt_text(doc.get("api_key") or "").strip()),
            "config": config,
            "updated_at": doc.get("updated_at"),
        })
    return integrations


def save_provider_config(
    user_id: int, platform: str, provider_name: str, *,
    auth_type: str = "api_key", credentials: Dict[str, Any] | None = None,
    config: Dict[str, Any] | None = None, priority: int = 100,
    is_active: bool = True, keep_existing_credentials_if_blank: bool = False,
    workspace_id: int | None = None,
) -> None:
    platform = (platform or "").strip().lower()
    provider_name = (provider_name or "").strip().lower()
    if not platform or not provider_name:
        raise ValueError("platform and provider_name are required")

    clean_credentials = {k: v for k, v in (credentials or {}).items() if str(v or "").strip()}
    encrypted_config = encrypt_text(json.dumps(config or {}))
    now = utc_now()
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    col = get_collection("provider_configs")
    existing = col.find_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "platform": platform, "provider_name": provider_name})
    if keep_existing_credentials_if_blank and not clean_credentials and existing:
        encrypted_credentials = existing.get("encrypted_credentials") or ""
    else:
        encrypted_credentials = encrypt_text(json.dumps(clean_credentials))
    col.update_one(
        {"user_id": user_id, "workspace_id": scoped_workspace_id, "platform": platform, "provider_name": provider_name},
        {"$set": {
            "organization_id": organization_id, "auth_type": auth_type,
            "encrypted_credentials": encrypted_credentials, "config_json": encrypted_config,
            "priority": int(priority), "is_active": 1 if is_active else 0,
            "updated_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    add_audit_log(
        user_id, "provider_config.upsert", "provider_config",
        f"{platform}:{provider_name}",
        {"platform": platform, "provider_name": provider_name, "auth_type": auth_type, "has_credentials": bool(clean_credentials)},
        workspace_id=scoped_workspace_id, organization_id=organization_id,
    )


def _provider_row_to_dict(doc, *, include_credentials: bool = False) -> dict[str, Any]:
    item = _strip_id(doc)
    config = _safe_json_loads(decrypt_text(item.get("config_json") or "{}"), {})
    credentials = _safe_json_loads(decrypt_text(item.get("encrypted_credentials") or "{}"), {})
    item["config"] = config
    item["has_credentials"] = bool(credentials)
    item["is_active"] = bool(item.get("is_active"))
    item.pop("encrypted_credentials", None)
    item.pop("config_json", None)
    if include_credentials:
        item["credentials"] = credentials
    return item


def get_provider_config(user_id: int, platform: str, provider_name: str, *, include_credentials: bool = False, workspace_id: int | None = None) -> dict[str, Any]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    doc = get_collection("provider_configs").find_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "platform": platform.lower(), "provider_name": provider_name.lower()})
    return _provider_row_to_dict(doc, include_credentials=include_credentials) if doc else {}


def list_provider_configs(user_id: int, platform: str | None = None, *, include_credentials: bool = False, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    q: dict[str, Any] = {"user_id": user_id, "workspace_id": scoped_workspace_id}
    if platform:
        q["platform"] = platform.lower()
    docs = get_collection("provider_configs").find(q).sort([("platform", pymongo.ASCENDING), ("priority", pymongo.ASCENDING), ("provider_name", pymongo.ASCENDING)])
    return [_provider_row_to_dict(d, include_credentials=include_credentials) for d in docs]


def delete_provider_config(user_id: int, platform: str, provider_name: str, workspace_id: int | None = None) -> None:
    platform = platform.lower()
    provider_name = provider_name.lower()
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    get_collection("provider_configs").delete_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "platform": platform, "provider_name": provider_name})
    add_audit_log(user_id, "provider_config.delete", "provider_config", f"{platform}:{provider_name}", {}, workspace_id=scoped_workspace_id, organization_id=organization_id)


def record_provider_health(
    user_id: int, platform: str, provider_name: str, health_status: str, *,
    latency_ms: int | None = None, error_message: str = "", workspace_id: int | None = None,
) -> None:
    now = utc_now()
    platform = platform.lower()
    provider_name = provider_name.lower()
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    col = get_collection("provider_configs")
    doc = col.find_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "platform": platform, "provider_name": provider_name})
    if not doc:
        return
    success_count = int(doc.get("success_count") or 0)
    failure_count = int(doc.get("failure_count") or 0)
    last_success_at = None
    last_failure_at = None
    if health_status == "healthy":
        success_count += 1
        last_success_at = now
    elif health_status in {"failed", "missing_credentials", "unhealthy"}:
        failure_count += 1
        last_failure_at = now
    update: dict[str, Any] = {
        "health_status": health_status, "last_health_check_at": now,
        "success_count": success_count, "failure_count": failure_count,
        "latency_ms": latency_ms, "last_error": error_message, "updated_at": now,
    }
    if last_success_at:
        update["last_success_at"] = last_success_at
    if last_failure_at:
        update["last_failure_at"] = last_failure_at
    col.update_one(
        {"user_id": user_id, "workspace_id": scoped_workspace_id, "platform": platform, "provider_name": provider_name},
        {"$set": update},
    )


def save_gmail_messages(user_id: int, messages: list[Dict[str, Any]]) -> list[dict[str, Any]]:
    from job_assistant.services.opportunity_classifier import annotate_opportunity, extract_opportunities_from_container

    saved: list[dict[str, Any]] = []
    now = utc_now()
    col = get_collection("gmail_messages")
    for message in messages:
        message = dict(message)
        message_id = str(message.get("message_id") or message.get("id") or "")
        thread_id = str(message.get("thread_id") or message.get("threadId") or "")
        open_url = message.get("open_url") or (f"https://mail.google.com/mail/u/0/#inbox/{thread_id or message_id}" if (thread_id or message_id) else "")
        classification = annotate_opportunity({
            "title": message.get("subject", ""),
            "subject": message.get("subject", ""),
            "sender": message.get("sender") or message.get("from") or "",
            "snippet": message.get("snippet", ""),
            "body": message.get("body", ""),
            "source": "Gmail",
            "source_type": "gmail",
            "message_id": message_id,
            "open_url": open_url,
        })
        extracted = extract_opportunities_from_container({**classification, **message, "open_url": open_url, "source": "Gmail", "source_type": "gmail"})
        message.update({
            "classification": classification.get("classification"),
            "classification_confidence": classification.get("classification_confidence"),
            "classification_reason": classification.get("classification_reason"),
            "opportunity_confidence": classification.get("opportunity_confidence"),
            "importable": classification.get("importable"),
            "blocked_reason": classification.get("blocked_reason"),
            "extracted_opportunities_count": len(extracted),
            "extracted_opportunities": extracted,
        })
        gid = _next_id("gmail_message_id")
        doc = {
            "gmail_message_id": gid, "user_id": user_id,
            "message_id": message_id, "thread_id": thread_id,
            "sender": message.get("sender") or message.get("from") or "",
            "subject": message.get("subject", ""),
            "date": message.get("date", ""),
            "snippet": message.get("snippet", ""),
            "open_url": open_url,
            "payload_json": json.dumps(message),
            "created_at": now,
        }
        try:
            col.insert_one(doc)
        except pymongo_errors.DuplicateKeyError:
            col.update_one({"user_id": user_id, "message_id": message_id}, {"$set": doc})
        saved.append({"id": gid, **message, "open_url": open_url, "created_at": now})
    return saved


def list_gmail_messages(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    docs = get_collection("gmail_messages").find({"user_id": user_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]
