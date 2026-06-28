from __future__ import annotations

from typing import Any, Dict

import pymongo

from job_assistant.db.core import (
    _next_id, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
)

__all__ = [
    "create_post", "list_posts",
]


def create_post(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    now = utc_now()
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id or payload.get("workspace_id"))
    pid = _next_id("post_id")
    get_collection("posts").insert_one({
        "post_id": pid, "user_id": user_id, "workspace_id": scoped_workspace_id,
        "organization_id": organization_id,
        "title": payload.get("title") or "",
        "base_content": payload.get("base_content") or payload.get("content") or "",
        "status": payload.get("status") or "draft",
        "scheduled_at": payload.get("scheduled_at") or None,
        "created_at": now, "updated_at": now,
    })
    for target in payload.get("targets") or []:
        get_collection("post_targets").insert_one({
            "post_id": pid,
            "platform": target.get("platform") or "",
            "provider_name": target.get("provider_name") or "",
            "transformed_content": target.get("transformed_content") or payload.get("base_content") or payload.get("content") or "",
            "status": target.get("status") or "pending",
            "created_at": now, "updated_at": now,
        })
    add_audit_log(user_id, "post.create", "post", str(pid), {"status": payload.get("status") or "draft"}, workspace_id=scoped_workspace_id, organization_id=organization_id)
    return pid


def list_posts(user_id: int, workspace_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("posts").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    posts = []
    for doc in docs:
        item = _strip_id(doc)
        targets = list(get_collection("post_targets").find({"post_id": item["post_id"]}).sort("_id", pymongo.ASCENDING))
        item["targets"] = [_strip_id(t) for t in targets]
        posts.append(item)
    return posts
