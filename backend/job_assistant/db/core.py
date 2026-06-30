from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

import pymongo
from pymongo import MongoClient, errors as pymongo_errors

from job_assistant.config import settings

__all__ = [
    "MONGO_URL", "MONGO_DB_NAME",
    "_client", "_db",
    "get_client", "get_db", "get_collection",
    "STATUSES", "OPPORTUNITY_TYPES", "JOB_LIKE_TYPES",
    "DEFAULT_USER_EMAIL", "DEFAULT_LOCAL_PASSWORD", "PASSWORD_HASH_ITERATIONS",
    "utc_now", "_next_id", "connect",
    "_ensure_indexes", "_ensure_default_user",
    "_hash_default_password",
    "_table_columns", "_add_column_if_missing",
    "init_db",
    "_strip_id",
    "_safe_json_loads",
    "_as_text",
    "_token_hash",
    "_workspace_scope_for_user",
    "add_audit_log",
    "db_health", "storage_health",
]

MONGO_URL = settings.mongo_url or "mongodb://localhost:27017"
MONGO_DB_NAME = settings.mongo_db_name or "career_assistant"

_client: MongoClient | None = None
_db = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    return _client


def get_db():
    global _db
    if _db is None:
        _db = get_client()[MONGO_DB_NAME]
    return _db


def get_collection(name: str):
    return get_db()[name]


STATUSES = ["New", "Reviewed", "Needs Review", "Non-Opportunity", "Apply manually", "Applied", "Interview", "Rejected", "Offer", "Archived", "Skip"]
OPPORTUNITY_TYPES = ["job", "internship", "contract", "freelance", "hackathon", "competition", "grant", "scholarship", "webinar", "event", "newsletter", "blog_post", "marketing_email", "announcement", "unknown", "other"]
JOB_LIKE_TYPES = ("job", "internship", "contract", "freelance")
DEFAULT_USER_EMAIL = "local@example.com"
DEFAULT_LOCAL_PASSWORD = os.getenv("LOCAL_USER_PASSWORD", "ChangeMe123!")
PASSWORD_HASH_ITERATIONS = 600_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _next_id(sequence: str) -> int:
    result = get_collection("counters").find_one_and_update(
        {"_id": sequence},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER,
    )
    return result["seq"]


@contextmanager
def connect(path=None):
    yield None


def _ensure_indexes() -> None:
    coll = get_db()

    coll.users.create_index("email", unique=True)
    coll.users.create_index("lower_email")
    coll.profiles.create_index([("user_id", pymongo.ASCENDING), ("name", pymongo.ASCENDING)], unique=True)
    coll.profiles.create_index("user_id")
    coll.jobs.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING), ("url", pymongo.ASCENDING)], unique=True)
    coll.jobs.create_index("user_id")
    coll.jobs.create_index("workspace_id")
    coll.jobs.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING), ("normalized_title", pymongo.ASCENDING)])
    coll.evaluations.create_index("job_id", unique=True)
    coll.application_materials.create_index("job_id", unique=True)
    coll.applications.create_index("job_id", unique=True)
    coll.reminders.create_index("job_id")
    coll.resume_reviews.create_index([("user_id", pymongo.ASCENDING), ("job_id", pymongo.ASCENDING)])
    coll.interview_prep_sessions.create_index([("user_id", pymongo.ASCENDING), ("job_id", pymongo.ASCENDING)])
    coll.recordings.create_index([("user_id", pymongo.ASCENDING), ("job_id", pymongo.ASCENDING)])
    coll.gmail_messages.create_index([("user_id", pymongo.ASCENDING), ("message_id", pymongo.ASCENDING)])
    coll.user_sessions.create_index("token_hash", unique=True)
    coll.user_sessions.create_index("expires_at")
    coll.password_reset_tokens.create_index("token_hash", unique=True)
    coll.integration_settings.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING), ("service", pymongo.ASCENDING)], unique=True)
    coll.provider_configs.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING), ("platform", pymongo.ASCENDING), ("provider_name", pymongo.ASCENDING)], unique=True)
    coll.automation_preferences.create_index("user_id", unique=True)
    coll.automation_rules.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.automation_runs.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.automation_steps.create_index("run_id")
    coll.automation_errors.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.activity_events.create_index("user_id")
    coll.feedback.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.score_feedback.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.audit_logs.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.ai_generations.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.prompt_versions.create_index([("name", pymongo.ASCENDING), ("version", pymongo.ASCENDING)], unique=True)
    coll.usage_counters.create_index([("resource_type", pymongo.ASCENDING), ("window_end", pymongo.ASCENDING)])
    coll.system_metrics.create_index([("metric_name", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)])
    coll.alert_events.create_index([("status", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)])
    coll.worker_jobs.create_index([("status", pymongo.ASCENDING), ("queue_name", pymongo.ASCENDING), ("run_after", pymongo.ASCENDING)])
    coll.organizations.create_index("slug", unique=True)
    coll.workspaces.create_index([("organization_id", pymongo.ASCENDING), ("slug", pymongo.ASCENDING)], unique=True)
    coll.workspace_members.create_index([("workspace_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING)], unique=True)
    coll.shared_resources.create_index([("workspace_id", pymongo.ASCENDING), ("resource_type", pymongo.ASCENDING), ("resource_id", pymongo.ASCENDING)], unique=True)
    coll.posts.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.post_targets.create_index("post_id")
    coll.compliance_exports.create_index("user_id")
    coll.conversations.create_index([("user_id", pymongo.ASCENDING), ("updated_at", pymongo.DESCENDING)])
    coll.conversation_messages.create_index([("conversation_id", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)])
    coll.agent_feedback.create_index([("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
    coll.agent_personas.create_index("user_id", unique=True)
    coll.agent_memory.create_index([("user_id", pymongo.ASCENDING), ("key", pymongo.ASCENDING)], unique=True)
    coll.agent_memory.create_index([("user_id", pymongo.ASCENDING), ("updated_at", pymongo.DESCENDING)])

    # Loops & auto-apply
    coll.loops.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.loops.create_index([("user_id", pymongo.ASCENDING), ("is_active", pymongo.ASCENDING), ("auto_apply_enabled", pymongo.ASCENDING)])
    coll.loop_runs.create_index([("loop_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.auto_apply_logs.create_index([("user_id", pymongo.ASCENDING), ("workspace_id", pymongo.ASCENDING)])
    coll.auto_apply_logs.create_index([("loop_id", pymongo.ASCENDING), ("user_id", pymongo.ASCENDING)])
    coll.auto_apply_logs.create_index([("user_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])


def _ensure_default_user() -> dict[str, Any]:
    users = get_collection("users")
    user = users.find_one({"email": DEFAULT_USER_EMAIL})
    if user:
        user_id = int(user["user_id"])
        if str(user.get("password_hash", "")).startswith("legacy:"):
            users.update_one({"user_id": user_id}, {"$set": {"password_hash": _hash_default_password(DEFAULT_LOCAL_PASSWORD), "updated_at": utc_now()}})
        return user
    now = utc_now()
    user_id = _next_id("user_id")
    doc = {
        "user_id": user_id,
        "email": DEFAULT_USER_EMAIL,
        "lower_email": DEFAULT_USER_EMAIL.lower(),
        "password_hash": _hash_default_password(DEFAULT_LOCAL_PASSWORD),
        "full_name": "Local User",
        "is_active": 1,
        "created_at": now,
        "updated_at": now,
    }
    users.insert_one(doc)
    return doc


def _hash_default_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_HASH_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest.hex()}"


def _table_columns(con, table: str) -> set[str]:
    return set()


def _add_column_if_missing(con, table: str, column: str, definition: str) -> None:
    pass


def init_db() -> None:
    _ensure_indexes()
    _ensure_default_user()


def _strip_id(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc = dict(doc)
        doc.pop("_id", None)
    return doc


def _safe_json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _workspace_scope_for_user(user_id: int, workspace_id: int | None = None) -> tuple[int, int]:
    from job_assistant.db.enterprise import _ensure_personal_workspace
    ws = _ensure_personal_workspace(user_id)
    if workspace_id is None:
        return int(ws["workspace_id"]), int(ws["organization_id"])
    wm = get_collection("workspace_members").find_one({"workspace_id": workspace_id, "user_id": user_id, "status": "active"})
    if not wm:
        raise PermissionError("You do not have access to this workspace")
    w = get_collection("workspaces").find_one({"workspace_id": workspace_id})
    return int(workspace_id), int(w["organization_id"]) if w else 0


def add_audit_log(
    user_id: int | None, action: str, resource_type: str = "",
    resource_id: str = "", metadata: Dict[str, Any] | None = None,
    ip_address: str = "", user_agent: str = "", con=None,
    workspace_id: int | None = None, organization_id: int | None = None,
) -> None:
    aid = _next_id("audit_log_id")
    get_collection("audit_logs").insert_one({
        "audit_log_id": aid, "user_id": user_id, "action": action,
        "resource_type": resource_type, "resource_id": resource_id,
        "ip_address": ip_address, "user_agent": user_agent,
        "metadata_json": json.dumps(metadata or {}),
        "created_at": utc_now(), "workspace_id": workspace_id,
        "organization_id": organization_id,
    })


def db_health() -> dict[str, Any]:
    started = utc_now()
    col = get_collection("users")
    users_count = col.count_documents({})
    feedback_count = get_collection("feedback").count_documents({})
    usage_count = get_collection("usage_counters").count_documents({})
    return {"status": "ok", "checked_at": started, "users": users_count, "feedback": feedback_count, "usage_counters": usage_count}


def storage_health() -> dict[str, Any]:
    return {"status": "ok", "database": "mongodb", "database_url": MONGO_URL}
