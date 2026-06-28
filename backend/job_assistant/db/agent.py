from __future__ import annotations

import json
from typing import Any

import pymongo

from job_assistant.db.core import _next_id, _strip_id, add_audit_log, get_collection, utc_now

__all__ = [
    "CONVERSATION_STATES",
    "create_conversation", "list_conversations", "get_conversation",
    "update_conversation", "delete_conversation",
    "add_conversation_message", "get_conversation_messages",
    "set_conversation_state", "_conversation_with_id_alias",
    "record_agent_feedback",
    "update_agent_persona", "get_agent_persona",
    "create_memory", "list_memories", "update_memory", "delete_memory",
    "get_memories_context",
    "MAX_MEMORIES_PER_USER",
]

CONVERSATION_STATES = {"idle", "searching", "tailoring", "interviewing", "chatting"}


def create_conversation(user_id: int, title: str, workspace_id: int | None = None) -> int:
    cid = _next_id("conversation_id")
    now = utc_now()
    get_collection("conversations").insert_one({
        "conversation_id": cid, "user_id": user_id, "workspace_id": workspace_id,
        "title": title, "state": "idle", "created_at": now, "updated_at": now,
    })
    return cid


def list_conversations(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    docs = get_collection("conversations").find({"user_id": user_id}).sort("updated_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 200)))
    return [_conversation_with_id_alias(d) for d in docs]


def get_conversation(conversation_id: int, user_id: int) -> dict[str, Any]:
    doc = get_collection("conversations").find_one({"conversation_id": conversation_id, "user_id": user_id})
    return _conversation_with_id_alias(doc) if doc else {}


def update_conversation(conversation_id: int, user_id: int, data: dict[str, Any]) -> bool:
    data["updated_at"] = utc_now()
    result = get_collection("conversations").update_one(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"$set": data},
    )
    return result.modified_count > 0


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    result = get_collection("conversations").delete_one({"conversation_id": conversation_id, "user_id": user_id})
    get_collection("conversation_messages").delete_many({"conversation_id": conversation_id})
    return result.deleted_count > 0


def add_conversation_message(conversation_id: int, role: str, content: str, sections: list[dict[str, Any]] | None = None) -> int:
    mid = _next_id("conversation_message_id")
    now = utc_now()
    get_collection("conversation_messages").insert_one({
        "message_id": mid, "conversation_id": conversation_id,
        "role": role, "content": content,
        "sections_json": json.dumps(sections or []),
        "created_at": now,
    })
    get_collection("conversations").update_one(
        {"conversation_id": conversation_id},
        {"$set": {"updated_at": now}},
    )
    return mid


def get_conversation_messages(conversation_id: int, limit: int = 100) -> list[dict[str, Any]]:
    docs = get_collection("conversation_messages").find(
        {"conversation_id": conversation_id}
    ).sort("created_at", pymongo.ASCENDING).limit(max(1, min(int(limit), 500)))
    result = []
    for doc in docs:
        item = {
            "id": doc["message_id"],
            "conversation_id": doc["conversation_id"],
            "role": doc["role"],
            "content": doc["content"],
            "sections": json.loads(doc.get("sections_json") or "[]"),
            "created_at": doc.get("created_at"),
        }
        result.append(item)
    return result


def set_conversation_state(conversation_id: int, user_id: int, state: str) -> bool:
    if state not in CONVERSATION_STATES:
        return False
    result = get_collection("conversations").update_one(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"$set": {"state": state, "updated_at": utc_now()}},
    )
    return result.modified_count > 0


def _conversation_with_id_alias(doc: dict) -> dict:
    item = _strip_id(doc)
    if item and "conversation_id" in item:
        item["id"] = item["conversation_id"]
    return item


def record_agent_feedback(user_id: int, conversation_id: int, message_id: int, rating: str, workspace_id: int | None = None) -> int:
    rating = (rating or "").strip().lower()
    if rating not in ("thumbs_up", "thumbs_down"):
        raise ValueError("rating must be 'thumbs_up' or 'thumbs_down'")
    fid = _next_id("agent_feedback_id")
    get_collection("agent_feedback").insert_one({
        "agent_feedback_id": fid, "user_id": user_id,
        "workspace_id": workspace_id, "conversation_id": conversation_id,
        "message_id": message_id, "rating": rating, "created_at": utc_now(),
    })
    return fid


def update_agent_persona(user_id: int, persona: dict[str, Any]) -> None:
    allowed_keys = {"tone", "detail_level", "focus_area"}
    clean = {k: v for k, v in persona.items() if k in allowed_keys}
    if not clean:
        return
    get_collection("agent_personas").update_one(
        {"user_id": user_id},
        {"$set": {**clean, "updated_at": utc_now()}},
        upsert=True,
    )


def get_agent_persona(user_id: int) -> dict[str, Any]:
    doc = get_collection("agent_personas").find_one({"user_id": user_id})
    if doc:
        return {k: v for k, v in doc.items() if k in ("tone", "detail_level", "focus_area")}
    return {}


MAX_MEMORIES_PER_USER = 50


def create_memory(user_id: int, key: str, value: str, source: str = "manual") -> int:
    key = (key or "").strip().lower()
    value = (value or "").strip()
    if not key or not value:
        raise ValueError("Key and value are required")
    if source not in ("manual", "extracted"):
        source = "manual"
    now = utc_now()
    col = get_collection("agent_memory")
    existing = col.find_one({"user_id": user_id, "key": key})
    if existing:
        col.update_one({"user_id": user_id, "key": key}, {"$set": {"value": value, "source": source, "updated_at": now}})
        return int(existing["memory_id"])
    count = col.count_documents({"user_id": user_id})
    if count >= MAX_MEMORIES_PER_USER:
        oldest = col.find_one({"user_id": user_id}, sort=[("updated_at", pymongo.ASCENDING)])
        if oldest:
            col.delete_one({"_id": oldest["_id"]})
    mid = _next_id("agent_memory_id")
    col.insert_one({"memory_id": mid, "user_id": user_id, "key": key, "value": value, "source": source, "created_at": now, "updated_at": now})
    return mid


def list_memories(user_id: int) -> list[dict[str, Any]]:
    docs = get_collection("agent_memory").find({"user_id": user_id}).sort("updated_at", pymongo.DESCENDING)
    return [_strip_id(d) for d in docs]


def update_memory(memory_id: int, user_id: int, key: str, value: str) -> bool:
    key = (key or "").strip().lower()
    value = (value or "").strip()
    if not key or not value:
        raise ValueError("Key and value are required")
    now = utc_now()
    result = get_collection("agent_memory").update_one(
        {"memory_id": memory_id, "user_id": user_id},
        {"$set": {"key": key, "value": value, "updated_at": now}},
    )
    return result.modified_count > 0


def delete_memory(memory_id: int, user_id: int) -> bool:
    result = get_collection("agent_memory").delete_one({"memory_id": memory_id, "user_id": user_id})
    return result.deleted_count > 0


def get_memories_context(user_id: int) -> str:
    docs = get_collection("agent_memory").find({"user_id": user_id}).sort("updated_at", pymongo.DESCENDING).limit(30)
    lines = []
    for doc in docs:
        key = doc.get("key", "")
        value = str(doc.get("value", ""))[:300]
        if key and value:
            lines.append(f"  - {key}: {value}")
    if not lines:
        return ""
    return "Things I know about this user:\n" + "\n".join(lines)
