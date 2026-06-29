from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from job_assistant.config import settings
from job_assistant.db import _next_id, add_audit_log, get_collection, utc_now
from job_assistant.provider_registry import BaseProvider, ProviderExecutionResult, provider_registry


PLATFORM_LIMITS = {
    "linkedin": {"characters": 3000, "media": 9},
    "x": {"characters": 280, "media": 4},
    "twitter": {"characters": 280, "media": 4},
    "reddit": {"characters": 40000, "media": 1},
    "facebook": {"characters": 63206, "media": 10},
    "instagram": {"characters": 2200, "media": 10},
    "threads": {"characters": 500, "media": 10},
    "mastodon": {"characters": 500, "media": 4},
    "bluesky": {"characters": 300, "media": 4},
    "discord": {"characters": 2000, "media": 10},
    "slack": {"characters": 4000, "media": 10},
    "telegram": {"characters": 4096, "media": 10},
    "medium": {"characters": 100000, "media": 20},
    "custom": {"characters": 100000, "media": 20},
}


@dataclass
class PublishValidation:
    ok: bool
    errors: list[str]
    warnings: list[str]


def validate_target(platform: str, content: str, media_count: int = 0) -> PublishValidation:
    rules = PLATFORM_LIMITS.get((platform or "custom").lower(), PLATFORM_LIMITS["custom"])
    errors = []
    warnings = []
    if not content.strip():
        errors.append("Content is required.")
    if len(content) > int(rules["characters"]):
        errors.append(f"{platform} content exceeds {rules['characters']} characters.")
    if media_count > int(rules["media"]):
        errors.append(f"{platform} media exceeds {rules['media']} attachments.")
    if "api_key" in content.lower() or "token" in content.lower():
        warnings.append("Content may contain sensitive credential-like text.")
    return PublishValidation(ok=not errors, errors=errors, warnings=warnings)


def get_post(user_id: int, post_id: int) -> dict[str, Any]:
    post = get_collection("posts").find_one({"_id": post_id, "user_id": user_id})
    if not post:
        return {}
    post["id"] = post["_id"]
    targets = list(get_collection("post_targets").find({"post_id": post_id}).sort("_id", 1))
    for t in targets:
        t["id"] = t["_id"]
    post["targets"] = targets
    return post


def approve_post(user_id: int, post_id: int) -> None:
    now = utc_now()
    post = get_collection("posts").find_one({"_id": post_id, "user_id": user_id})
    if not post:
        raise ValueError("Post not found")
    get_collection("posts").update_one({"_id": post_id}, {"$set": {"status": "approved", "updated_at": now}})
    get_collection("post_targets").update_many(
        {"post_id": post_id, "status": {"$in": ["pending", "draft"]}},
        {"$set": {"status": "approved", "updated_at": now}},
    )
    add_audit_log(user_id, "post.approve", "post", str(post_id), {}, workspace_id=post.get("workspace_id"), organization_id=post.get("organization_id"))


class LinkedInProvider(BaseProvider):
    provider_name = "linkedin"
    platform = "linkedin"
    supported_actions = {"publish_post"}

    def execute(self, action: str, payload: dict[str, Any]) -> Any:
        from job_assistant.services.linkedin_integration import publish_text_post
        api_token = (self.credentials.get("api_key") or self.credentials.get("access_token") or "").strip()
        author_urn = (self.config.get("author_urn") or "").strip()
        if not api_token:
            raise ValueError("LinkedIn API token is not configured.")
        if not author_urn:
            raise ValueError("LinkedIn author URN is not configured.")
        content = str(payload.get("content") or "")
        result = publish_text_post(api_token, author_urn, content)
        return {"status": "published", "platform": "linkedin", "post_id": result.get("post_id", "")}


provider_registry.register("linkedin", "linkedin", LinkedInProvider)


def publish_post(user_id: int, post_id: int, *, dry_run: bool | None = None) -> dict[str, Any]:
    dry = settings.publishing_dry_run if dry_run is None else dry_run
    post = get_post(user_id, post_id)
    if not post:
        raise ValueError("Post not found")
    if settings.publishing_require_approval and post.get("status") != "approved":
        raise PermissionError("Post must be approved before publishing.")
    results = []
    now = utc_now()
    for target in post.get("targets", []):
        content = target.get("transformed_content") or post.get("base_content") or ""
        validation = validate_target(target.get("platform") or "custom", content)
        if not validation.ok:
            get_collection("post_targets").update_one(
                {"_id": target["id"]},
                {"$set": {"status": "failed", "error_message": "; ".join(validation.errors), "updated_at": now}},
            )
            results.append({"target_id": target["id"], "status": "failed", "errors": validation.errors})
            continue
        if dry:
            get_collection("post_targets").update_one(
                {"_id": target["id"]},
                {"$set": {"status": "dry_run", "error_message": "", "updated_at": now}},
            )
            results.append({"target_id": target["id"], "status": "dry_run", "warnings": validation.warnings})
            continue
        result = provider_registry.execute_with_fallback(
            user_id,
            target.get("platform") or "custom",
            "publish_post",
            {"content": content, "post_id": post_id, "target_id": target["id"]},
            workspace_id=post.get("workspace_id"),
        )
        status = "published" if result.ok else "failed"
        get_collection("post_targets").update_one(
            {"_id": target["id"]},
            {"$set": {"status": status, "provider_name": result.provider_name, "error_message": result.error, "published_url": "", "updated_at": now}},
        )
        results.append({"target_id": target.get("id"), "status": status, "provider": result.provider_name, "error": result.error})
    final_status = "published" if results and all(r["status"] == "published" for r in results) else "reviewed"
    if dry:
        final_status = "dry_run"
    get_collection("posts").update_one({"_id": post_id}, {"$set": {"status": final_status, "updated_at": now}})
    add_audit_log(user_id, "post.publish_dry_run" if dry else "post.publish", "post", str(post_id), {"results": results}, workspace_id=post.get("workspace_id"), organization_id=post.get("organization_id"))
    return {"post_id": post_id, "dry_run": dry, "results": results}
