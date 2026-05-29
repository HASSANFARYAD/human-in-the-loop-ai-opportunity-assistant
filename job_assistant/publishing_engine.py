from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from job_assistant.config import settings
from job_assistant.db import add_audit_log, connect, utc_now
from job_assistant.provider_registry import provider_registry


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
    with connect() as con:
        post = con.execute("SELECT * FROM posts WHERE id=? AND user_id=?", (post_id, user_id)).fetchone()
        if not post:
            return {}
        item = dict(post)
        targets = con.execute("SELECT * FROM post_targets WHERE post_id=? ORDER BY id", (post_id,)).fetchall()
        item["targets"] = [dict(t) for t in targets]
        return item


def approve_post(user_id: int, post_id: int) -> None:
    now = utc_now()
    with connect() as con:
        post = con.execute("SELECT * FROM posts WHERE id=? AND user_id=?", (post_id, user_id)).fetchone()
        if not post:
            raise ValueError("Post not found")
        con.execute("UPDATE posts SET status='approved', updated_at=? WHERE id=?", (now, post_id))
        con.execute("UPDATE post_targets SET status='approved', updated_at=? WHERE post_id=? AND status IN ('pending','draft')", (now, post_id))
        add_audit_log(user_id, "post.approve", "post", str(post_id), {}, con=con, workspace_id=post["workspace_id"], organization_id=post["organization_id"])


def publish_post(user_id: int, post_id: int, *, dry_run: bool | None = None) -> dict[str, Any]:
    dry = settings.publishing_dry_run if dry_run is None else dry_run
    post = get_post(user_id, post_id)
    if not post:
        raise ValueError("Post not found")
    if settings.publishing_require_approval and post.get("status") != "approved":
        raise PermissionError("Post must be approved before publishing.")
    results = []
    now = utc_now()
    with connect() as con:
        for target in post.get("targets", []):
            content = target.get("transformed_content") or post.get("base_content") or ""
            validation = validate_target(target.get("platform") or "custom", content)
            if not validation.ok:
                con.execute("UPDATE post_targets SET status='failed', error_message=?, updated_at=? WHERE id=?", ("; ".join(validation.errors), now, target["id"]))
                results.append({"target_id": target["id"], "status": "failed", "errors": validation.errors})
                continue
            if dry:
                con.execute("UPDATE post_targets SET status='dry_run', error_message='', updated_at=? WHERE id=?", (now, target["id"]))
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
            con.execute(
                "UPDATE post_targets SET status=?, provider_name=COALESCE(provider_name, ?), error_message=?, published_url=?, updated_at=? WHERE id=?",
                (status, result.provider_name, result.error, "", now, target["id"]),
            )
            results.append({"target_id": target["id"], "status": status, "provider": result.provider_name, "error": result.error})
        final_status = "published" if results and all(r["status"] == "published" for r in results) else "reviewed"
        if dry:
            final_status = "dry_run"
        con.execute("UPDATE posts SET status=?, updated_at=? WHERE id=?", (final_status, now, post_id))
        add_audit_log(user_id, "post.publish_dry_run" if dry else "post.publish", "post", str(post_id), {"results": results}, con=con, workspace_id=post["workspace_id"], organization_id=post["organization_id"])
    return {"post_id": post_id, "dry_run": dry, "results": results}
