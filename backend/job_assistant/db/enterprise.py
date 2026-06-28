from __future__ import annotations

import secrets
from typing import Any, Dict

import pymongo

from job_assistant.db.core import (
    _next_id, _strip_id, add_audit_log, get_collection, utc_now,
)

__all__ = [
    "SYSTEM_ROLES", "SYSTEM_PERMISSIONS", "ROLE_PERMISSION_MAP",
    "_slugify", "_seed_roles_permissions",
    "_ensure_personal_workspace", "ensure_user_workspace",
    "list_roles", "list_permissions", "list_role_permissions",
    "create_organization", "create_workspace",
    "list_user_workspaces", "get_workspace_for_user",
    "list_workspace_members", "add_workspace_member",
    "user_has_permission",
    "share_resource", "list_shared_resources",
    "enterprise_summary",
]

SYSTEM_ROLES = [
    ("owner", "Full control over an organization/workspace."),
    ("admin", "Manage members, integrations, and workspace configuration."),
    ("manager", "Manage workflows and review team resources."),
    ("editor", "Create and edit content and workflow resources."),
    ("recruiter", "Manage opportunities and recruiting workflows."),
    ("moderator", "Review shared content and feedback."),
    ("analyst", "View analytics, audit activity, and reports."),
    ("contributor", "Create resources but cannot manage settings."),
    ("viewer", "Read-only workspace access."),
]

SYSTEM_PERMISSIONS = {
    "workspace:manage": "Manage workspace settings.",
    "workspace:invite": "Invite or add members to a workspace.",
    "member:read": "View workspace members.",
    "feedback:create": "Create feedback.",
    "feedback:read_all": "Read workspace feedback.",
    "integration:manage": "Manage provider and integration credentials.",
    "provider:manage": "Manage provider abstraction records.",
    "post:create": "Create draft publishing content.",
    "post:approve": "Approve content before publishing.",
    "post:publish": "Publish content through connected providers.",
    "automation:create": "Create automation rules.",
    "automation:run": "Run automation workflows.",
    "automation:disable": "Disable automation workflows.",
    "audit_log:view": "View audit logs.",
    "ai:generate": "Generate AI content.",
    "billing:manage": "Manage billing configuration.",
    "user:invite": "Invite users.",
    "shared_resource:create": "Share resources into a workspace.",
    "shared_resource:read": "Read shared workspace resources.",
}

ROLE_PERMISSION_MAP = {
    "owner": list(SYSTEM_PERMISSIONS.keys()),
    "admin": [p for p in SYSTEM_PERMISSIONS if p != "billing:manage"],
    "manager": ["member:read", "feedback:read_all", "post:create", "post:approve", "automation:create", "automation:run", "automation:disable", "audit_log:view", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "editor": ["post:create", "automation:run", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "recruiter": ["post:create", "automation:run", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "moderator": ["member:read", "feedback:read_all", "post:approve", "shared_resource:read"],
    "analyst": ["member:read", "audit_log:view", "shared_resource:read"],
    "contributor": ["post:create", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "viewer": ["shared_resource:read"],
}


def _slugify(value: str) -> str:
    text = ''.join(ch.lower() if ch.isalnum() else '-' for ch in (value or '').strip())
    while '--' in text:
        text = text.replace('--', '-')
    return text.strip('-') or f"item-{secrets.token_hex(4)}"


def _seed_roles_permissions() -> None:
    now = utc_now()
    roles_col = get_collection("roles")
    perms_col = get_collection("permissions")
    rp_col = get_collection("role_permissions")
    for role, description in SYSTEM_ROLES:
        roles_col.update_one({"name": role}, {"$set": {"name": role, "description": description, "is_system": 1, "updated_at": now}, "$setOnInsert": {"created_at": now}}, upsert=True)
    for perm, description in SYSTEM_PERMISSIONS.items():
        perms_col.update_one({"name": perm}, {"$set": {"name": perm, "description": description, "created_at": now}}, upsert=True)
    for role, permissions in ROLE_PERMISSION_MAP.items():
        for perm in permissions:
            rp_col.update_one({"role_name": role, "permission_name": perm}, {"$set": {"created_at": now}}, upsert=True)


def _ensure_personal_workspace(user_id: int, email: str = "", full_name: str = "") -> dict[str, Any]:
    wm = get_collection("workspace_members").find_one({"user_id": user_id, "role": "owner"})
    if wm:
        ws = get_collection("workspaces").find_one({"workspace_id": wm["workspace_id"]})
        org = get_collection("organizations").find_one({"organization_id": ws["organization_id"]}) if ws else None
        return {
            "organization_id": ws["organization_id"] if ws else 0,
            "organization_name": org.get("name", "") if org else "",
            "workspace_id": wm["workspace_id"],
            "workspace_name": ws.get("name", "") if ws else "",
        }
    now = utc_now()
    owner_label = full_name.strip() or (email.split('@')[0] if email else f"User {user_id}")
    org_name = f"{owner_label}'s Organization"
    org_slug_base = _slugify(f"{owner_label}-{user_id}")
    org_slug = org_slug_base
    orgs = get_collection("organizations")
    suffix = 1
    while orgs.find_one({"slug": org_slug}):
        suffix += 1
        org_slug = f"{org_slug_base}-{suffix}"
    org_id = _next_id("organization_id")
    orgs.insert_one({"organization_id": org_id, "name": org_name, "slug": org_slug, "owner_user_id": user_id, "created_at": now, "updated_at": now})
    ws_id = _next_id("workspace_id")
    get_collection("workspaces").insert_one({
        "workspace_id": ws_id, "organization_id": org_id,
        "name": "Personal Workspace", "slug": "personal",
        "description": "Default private workspace", "created_at": now, "updated_at": now,
    })
    get_collection("workspace_members").update_one(
        {"workspace_id": ws_id, "user_id": user_id},
        {"$set": {"role": "owner", "status": "active", "invited_by": user_id, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"organization_id": org_id, "organization_name": org_name, "workspace_id": ws_id, "workspace_name": "Personal Workspace"}


def ensure_user_workspace(user_id: int) -> dict[str, Any]:
    user = get_collection("users").find_one({"user_id": user_id})
    if not user:
        raise ValueError("User not found")
    _seed_roles_permissions()
    workspace = _ensure_personal_workspace(user_id, user.get("email", ""), user.get("full_name", ""))
    return workspace


def list_roles() -> list[dict[str, Any]]:
    _seed_roles_permissions()
    docs = list(get_collection("roles").aggregate([
        {"$addFields": {"sort_order": {"$switch": {
            "branches": [
                {"case": {"$eq": ["$name", "owner"]}, "then": 1},
                {"case": {"$eq": ["$name", "admin"]}, "then": 2},
                {"case": {"$eq": ["$name", "manager"]}, "then": 3},
            ],
            "default": 9,
        }}}},
        {"$sort": {"sort_order": 1, "name": 1}},
    ]))
    return [_strip_id(d) for d in docs]


def list_permissions() -> list[dict[str, Any]]:
    _seed_roles_permissions()
    docs = get_collection("permissions").find().sort("name", pymongo.ASCENDING)
    return [_strip_id(d) for d in docs]


def list_role_permissions(role_name: str | None = None) -> list[dict[str, Any]]:
    _seed_roles_permissions()
    q = {"role_name": role_name} if role_name else {}
    docs = get_collection("role_permissions").find(q).sort([("role_name", pymongo.ASCENDING), ("permission_name", pymongo.ASCENDING)])
    return [_strip_id(d) for d in docs]


def create_organization(user_id: int, name: str) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Organization name is required")
    now = utc_now()
    slug_base = _slugify(name)
    slug = slug_base
    orgs = get_collection("organizations")
    suffix = 1
    while orgs.find_one({"slug": slug}):
        suffix += 1
        slug = f"{slug_base}-{suffix}"
    org_id = _next_id("organization_id")
    orgs.insert_one({"organization_id": org_id, "name": name, "slug": slug, "owner_user_id": user_id, "created_at": now, "updated_at": now})
    add_audit_log(user_id, "organization.create", "organization", str(org_id), {"name": name}, organization_id=org_id)
    return {"organization_id": org_id, "name": name, "slug": slug, "owner_user_id": user_id, "created_at": now, "updated_at": now}


def create_workspace(user_id: int, organization_id: int, name: str, description: str = "") -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Workspace name is required")
    now = utc_now()
    slug_base = _slugify(name)
    slug = slug_base
    org = get_collection("organizations").find_one({"organization_id": organization_id})
    if not org:
        raise ValueError("Organization not found")
    if int(org["owner_user_id"]) != int(user_id) and not user_has_permission(user_id, None, "workspace:manage", organization_id=organization_id):
        raise PermissionError("You do not have permission to create workspaces in this organization")
    workspaces = get_collection("workspaces")
    suffix = 1
    while workspaces.find_one({"organization_id": organization_id, "slug": slug}):
        suffix += 1
        slug = f"{slug_base}-{suffix}"
    ws_id = _next_id("workspace_id")
    workspaces.insert_one({
        "workspace_id": ws_id, "organization_id": organization_id,
        "name": name, "slug": slug, "description": description or "",
        "created_at": now, "updated_at": now,
    })
    get_collection("workspace_members").update_one(
        {"workspace_id": ws_id, "user_id": user_id},
        {"$set": {"role": "owner", "status": "active", "invited_by": user_id, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    add_audit_log(user_id, "workspace.create", "workspace", str(ws_id), {"name": name}, workspace_id=ws_id, organization_id=organization_id)
    return {"id": ws_id, "organization_id": organization_id, "name": name, "slug": slug, "description": description or "", "created_at": now, "updated_at": now}


def list_user_workspaces(user_id: int) -> list[dict[str, Any]]:
    ensure_user_workspace(user_id)
    pipeline = [
        {"$match": {"user_id": user_id, "status": "active"}},
        {"$lookup": {"from": "workspaces", "localField": "workspace_id", "foreignField": "workspace_id", "as": "workspace"}},
        {"$unwind": "$workspace"},
        {"$lookup": {"from": "organizations", "localField": "workspace.organization_id", "foreignField": "organization_id", "as": "org"}},
        {"$unwind": "$org"},
        {"$sort": {"org.name": 1, "workspace.name": 1}},
        {"$project": {
            "_id": 0, "id": "$workspace.workspace_id", "name": "$workspace.name",
            "slug": "$workspace.slug", "description": "$workspace.description",
            "created_at": "$workspace.created_at", "updated_at": "$workspace.updated_at",
            "organization_id": "$org.organization_id",
            "organization_name": "$org.name", "organization_slug": "$org.slug",
            "role": "$role", "status": "$status",
        }},
    ]
    return list(get_collection("workspace_members").aggregate(pipeline))


def get_workspace_for_user(user_id: int, workspace_id: int) -> dict[str, Any]:
    pipeline = [
        {"$match": {"workspace_id": workspace_id, "user_id": user_id, "status": "active"}},
        {"$lookup": {"from": "workspaces", "localField": "workspace_id", "foreignField": "workspace_id", "as": "workspace"}},
        {"$unwind": "$workspace"},
        {"$lookup": {"from": "organizations", "localField": "workspace.organization_id", "foreignField": "organization_id", "as": "org"}},
        {"$unwind": "$org"},
        {"$limit": 1},
        {"$project": {
            "_id": 0, "id": "$workspace.workspace_id", "name": "$workspace.name",
            "slug": "$workspace.slug", "description": "$workspace.description",
            "created_at": "$workspace.created_at", "updated_at": "$workspace.updated_at",
            "organization_id": "$org.organization_id", "organization_name": "$org.name",
            "role": "$role",
        }},
    ]
    docs = list(get_collection("workspace_members").aggregate(pipeline))
    return docs[0] if docs else {}


def list_workspace_members(user_id: int, workspace_id: int) -> list[dict[str, Any]]:
    if not user_has_permission(user_id, workspace_id, "member:read") and not user_has_permission(user_id, workspace_id, "workspace:manage"):
        raise PermissionError("You do not have permission to view workspace members")
    pipeline = [
        {"$match": {"workspace_id": workspace_id}},
        {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "user_id", "as": "user"}},
        {"$unwind": "$user"},
        {"$addFields": {"sort_order": {"$switch": {
            "branches": [
                {"case": {"$eq": ["$role", "owner"]}, "then": 1},
                {"case": {"$eq": ["$role", "admin"]}, "then": 2},
            ],
            "default": 9,
        }}}},
        {"$sort": {"sort_order": 1, "user.email": 1}},
        {"$project": {
            "_id": 0, "id": "$_id", "workspace_id": 1, "user_id": 1,
            "email": "$user.email", "full_name": "$user.full_name", "role": 1,
            "status": 1, "invited_by": 1, "created_at": 1, "updated_at": 1,
        }},
    ]
    return list(get_collection("workspace_members").aggregate(pipeline))


def add_workspace_member(actor_user_id: int, workspace_id: int, email: str, role: str = "viewer") -> dict[str, Any]:
    role = (role or "viewer").strip().lower()
    email = (email or "").strip().lower()
    if role not in {r[0] for r in SYSTEM_ROLES}:
        raise ValueError("Invalid role")
    if not email:
        raise ValueError("Member email is required")
    if not user_has_permission(actor_user_id, workspace_id, "workspace:invite") and not user_has_permission(actor_user_id, workspace_id, "workspace:manage"):
        raise PermissionError("You do not have permission to add workspace members")
    now = utc_now()
    user = get_collection("users").find_one({"lower_email": email})
    if not user:
        raise ValueError("User must create an account before they can be added to a workspace")
    target_user_id = int(user["user_id"])
    get_collection("workspace_members").update_one(
        {"workspace_id": workspace_id, "user_id": target_user_id},
        {"$set": {"role": role, "status": "active", "invited_by": actor_user_id, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    ws = get_collection("workspaces").find_one({"workspace_id": workspace_id})
    add_audit_log(actor_user_id, "workspace_member.upsert", "workspace_member", str(target_user_id), {"workspace_id": workspace_id, "role": role, "email": email}, workspace_id=workspace_id, organization_id=int(ws["organization_id"]) if ws else None)
    return {"workspace_id": workspace_id, "user_id": target_user_id, "email": email, "role": role, "status": "active"}


def user_has_permission(user_id: int, workspace_id: int | None, permission_name: str, *, organization_id: int | None = None, con=None) -> bool:
    _seed_roles_permissions()
    if workspace_id is not None:
        pipeline = [
            {"$match": {"workspace_id": workspace_id, "user_id": user_id, "status": "active"}},
            {"$lookup": {"from": "role_permissions", "localField": "role", "foreignField": "role_name", "as": "perms"}},
            {"$unwind": "$perms"},
            {"$match": {"perms.permission_name": permission_name}},
            {"$limit": 1},
        ]
        docs = list(get_collection("workspace_members").aggregate(pipeline))
        return len(docs) > 0
    elif organization_id is not None:
        pipeline = [
            {"$match": {"user_id": user_id, "status": "active"}},
            {"$lookup": {"from": "workspaces", "localField": "workspace_id", "foreignField": "workspace_id", "as": "ws"}},
            {"$unwind": "$ws"},
            {"$match": {"ws.organization_id": organization_id}},
            {"$lookup": {"from": "role_permissions", "localField": "role", "foreignField": "role_name", "as": "perms"}},
            {"$unwind": "$perms"},
            {"$match": {"perms.permission_name": permission_name}},
            {"$limit": 1},
        ]
        docs = list(get_collection("workspace_members").aggregate(pipeline))
        return len(docs) > 0
    return False


def share_resource(user_id: int, workspace_id: int, resource_type: str, resource_id: str, access_level: str = "read", expires_at: str = "") -> int:
    resource_type = (resource_type or "").strip().lower()
    resource_id = (resource_id or "").strip()
    access_level = (access_level or "read").strip().lower()
    if not resource_type or not resource_id:
        raise ValueError("resource_type and resource_id are required")
    if access_level not in {"read", "comment", "edit", "admin"}:
        access_level = "read"
    if not user_has_permission(user_id, workspace_id, "shared_resource:create"):
        raise PermissionError("You do not have permission to share resources in this workspace")
    ws = get_collection("workspaces").find_one({"workspace_id": workspace_id})
    now = utc_now()
    sr_id = _next_id("shared_resource_id")
    get_collection("shared_resources").update_one(
        {"workspace_id": workspace_id, "resource_type": resource_type, "resource_id": resource_id},
        {"$set": {"user_id": user_id, "access_level": access_level, "expires_at": expires_at or None, "created_at": now}},
        upsert=True,
    )
    existing = get_collection("shared_resources").find_one({"workspace_id": workspace_id, "resource_type": resource_type, "resource_id": resource_id})
    share_id = int(existing.get("shared_resource_id", sr_id)) if existing else sr_id
    add_audit_log(user_id, "shared_resource.upsert", "shared_resource", str(share_id), {"resource_type": resource_type, "resource_id": resource_id, "access_level": access_level}, workspace_id=workspace_id, organization_id=int(ws["organization_id"]) if ws else None)
    return share_id


def list_shared_resources(user_id: int, workspace_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    workspaces = list_user_workspaces(user_id)
    allowed_workspace_ids = {int(w["id"]) for w in workspaces if user_has_permission(user_id, int(w["id"]), "shared_resource:read")}
    if workspace_id is not None:
        if int(workspace_id) not in allowed_workspace_ids:
            raise PermissionError("You do not have access to this workspace")
        allowed_workspace_ids = {int(workspace_id)}
    if not allowed_workspace_ids:
        return []
    pipeline = [
        {"$match": {"workspace_id": {"$in": list(allowed_workspace_ids)}}},
        {"$lookup": {"from": "workspaces", "localField": "workspace_id", "foreignField": "workspace_id", "as": "w"}},
        {"$unwind": "$w"},
        {"$lookup": {"from": "organizations", "localField": "w.organization_id", "foreignField": "organization_id", "as": "o"}},
        {"$unwind": "$o"},
        {"$lookup": {"from": "users", "localField": "user_id", "foreignField": "user_id", "as": "u"}},
        {"$unwind": {"path": "$u", "preserveNullAndEmptyArrays": True}},
        {"$sort": {"created_at": pymongo.DESCENDING}},
        {"$limit": max(1, min(int(limit), 500))},
        {"$project": {
            "_id": 0, "workspace_id": 1, "resource_type": 1, "resource_id": 1,
            "access_level": 1, "created_at": 1, "expires_at": 1,
            "workspace_name": "$w.name", "organization_name": "$o.name",
            "shared_by_email": "$u.email",
        }},
    ]
    return list(get_collection("shared_resources").aggregate(pipeline))


def enterprise_summary(user_id: int) -> dict[str, Any]:
    ensure_user_workspace(user_id)
    workspaces = list_user_workspaces(user_id)
    workspace_ids = [int(w["id"]) for w in workspaces]
    q = {"workspace_id": {"$in": workspace_ids}} if workspace_ids else {"workspace_id": {"$in": [-1]}}
    member_count = len(get_collection("workspace_members").distinct("user_id", q)) if workspace_ids else 0
    shared_count = get_collection("shared_resources").count_documents(q) if workspace_ids else 0
    audit_count = get_collection("audit_logs").count_documents({"user_id": user_id})
    return {
        "workspaces": len(workspaces),
        "members": member_count,
        "shared_resources": shared_count,
        "audit_events": audit_count,
        "roles": len(SYSTEM_ROLES),
        "permissions": len(SYSTEM_PERMISSIONS),
    }
