from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from bson.objectid import ObjectId

import pymongo
from pymongo import MongoClient, errors as pymongo_errors
from pymongo.operations import UpdateOne

from job_assistant.config import settings
from job_assistant.crypto import decrypt_text, encrypt_text

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


def create_user(email: str, password_hash: str, full_name: str = "") -> int:
    now = utc_now()
    user_id = _next_id("user_id")
    get_collection("users").insert_one({
        "user_id": user_id,
        "email": email.strip().lower(),
        "lower_email": email.strip().lower(),
        "password_hash": password_hash,
        "full_name": full_name.strip(),
        "is_active": 1,
        "created_at": now,
        "updated_at": now,
    })
    return user_id


def _user_with_id_alias(doc: dict) -> dict:
    """Add 'id' as an alias for 'user_id' to maintain API compatibility."""
    item = _strip_id(doc)
    if item and "user_id" in item:
        item["id"] = item["user_id"]
    return item


def get_user_by_email(email: str) -> dict[str, Any]:
    doc = get_collection("users").find_one({"lower_email": email.strip().lower()})
    return _user_with_id_alias(doc) if doc else {}


def get_user(user_id: int) -> dict[str, Any]:
    doc = get_collection("users").find_one({"user_id": user_id, "is_active": 1})
    return _user_with_id_alias(doc) if doc else {}


def _strip_id(doc: dict) -> dict:
    if doc and "_id" in doc:
        doc = dict(doc)
        doc.pop("_id", None)
    return doc


PROFILE_FIELDS = [
    "cv_text", "target_roles", "industries", "locations", "remote_preference",
    "salary_expectations", "work_authorization", "years_experience", "skills",
    "deal_breakers", "full_name", "email", "preferred_role", "country",
    "job_preferences", "platforms", "resume_name", "integration_status",
]


def _default_profile_id(user_id: int) -> int | None:
    doc = get_collection("profiles").find_one({"user_id": user_id}, sort=[("is_default", pymongo.DESCENDING), ("_id", pymongo.ASCENDING)])
    return int(doc["profile_id"]) if doc else None


def upsert_profile(profile: Dict[str, Any], user_id: int = 1, profile_id: int | None = None) -> int:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    profiles = get_collection("profiles")
    target_id = profile_id or _default_profile_id(user_id)
    if target_id is not None:
        profiles.update_one({"profile_id": target_id, "user_id": user_id}, {"$set": {**values, "updated_at": now}})
        return int(target_id)
    name = (profile.get("name") or "Default").strip() or "Default"
    pid = _next_id("profile_id")
    profiles.insert_one({"profile_id": pid, "user_id": user_id, "name": name, "is_default": 1, **values, "created_at": now, "updated_at": now})
    return pid


def create_profile(user_id: int, profile: Dict[str, Any], name: str = "", make_default: bool = False) -> int:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    clean_name = (name or profile.get("name") or "").strip() or "New profile"
    profiles = get_collection("profiles")
    has_any = profiles.find_one({"user_id": user_id})
    is_default = 1 if (make_default or not has_any) else 0
    base, suffix = clean_name, 2
    while profiles.find_one({"user_id": user_id, "name": clean_name}):
        clean_name = f"{base} ({suffix})"
        suffix += 1
    if is_default:
        profiles.update_many({"user_id": user_id}, {"$set": {"is_default": 0}})
    pid = _next_id("profile_id")
    profiles.insert_one({"profile_id": pid, "user_id": user_id, "name": clean_name, "is_default": is_default, **values, "created_at": now, "updated_at": now})
    return pid


def update_profile_fields(user_id: int, profile_id: int, profile: Dict[str, Any]) -> bool:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    profiles = get_collection("profiles")
    existing = profiles.find_one({"profile_id": profile_id, "user_id": user_id})
    if not existing:
        return False
    updates = {**values, "updated_at": now}
    if profile.get("name"):
        new_name = profile["name"].strip()
        if new_name and not profiles.find_one({"user_id": user_id, "name": new_name, "profile_id": {"$ne": profile_id}}):
            updates["name"] = new_name
    profiles.update_one({"profile_id": profile_id, "user_id": user_id}, {"$set": updates})
    return True


def set_default_profile(user_id: int, profile_id: int) -> bool:
    profiles = get_collection("profiles")
    if not profiles.find_one({"profile_id": profile_id, "user_id": user_id}):
        return False
    profiles.update_many({"user_id": user_id}, {"$set": {"is_default": 0}})
    profiles.update_one({"profile_id": profile_id, "user_id": user_id}, {"$set": {"is_default": 1}})
    return True


def delete_profile(user_id: int, profile_id: int) -> bool:
    profiles = get_collection("profiles")
    count = profiles.count_documents({"user_id": user_id})
    if count <= 1:
        raise ValueError("Cannot delete your only profile.")
    doc = profiles.find_one({"profile_id": profile_id, "user_id": user_id})
    if not doc:
        return False
    profiles.delete_one({"profile_id": profile_id, "user_id": user_id})
    if doc.get("is_default"):
        next_profile = profiles.find_one({"user_id": user_id}, sort=[("_id", pymongo.DESCENDING)])
        if next_profile:
            profiles.update_one({"_id": next_profile["_id"]}, {"$set": {"is_default": 1}})
    return True


def _profile_with_id_alias(doc: dict) -> dict:
    """Add 'id' as an alias for 'profile_id' to maintain API compatibility."""
    item = _strip_id(doc)
    if item and "profile_id" in item:
        item["id"] = item["profile_id"]
    return item


def _job_with_id_alias(doc: dict) -> dict:
    """Add 'id' as an alias for 'job_id' to maintain API compatibility."""
    item = _strip_id(doc)
    if item and "job_id" in item:
        item["id"] = item["job_id"]
    return item


def list_profiles(user_id: int) -> list[dict[str, Any]]:
    docs = get_collection("profiles").find({"user_id": user_id}).sort([("is_default", pymongo.DESCENDING), ("name", pymongo.ASCENDING)])
    return [_profile_with_id_alias(d) for d in docs]


def get_profile(user_id: int = 1, profile_id: int | None = None) -> Dict[str, Any]:
    profiles = get_collection("profiles")
    if profile_id is not None:
        doc = profiles.find_one({"profile_id": profile_id, "user_id": user_id})
    else:
        doc = profiles.find_one({"user_id": user_id}, sort=[("is_default", pymongo.DESCENDING), ("_id", pymongo.ASCENDING)])
    return _profile_with_id_alias(doc) if doc else {}


def _workspace_scope_for_user(user_id: int, workspace_id: int | None = None) -> tuple[int, int]:
    ws = _ensure_personal_workspace(user_id)
    if workspace_id is None:
        return int(ws["workspace_id"]), int(ws["organization_id"])
    wm = get_collection("workspace_members").find_one({"workspace_id": workspace_id, "user_id": user_id, "status": "active"})
    if not wm:
        raise PermissionError("You do not have access to this workspace")
    w = get_collection("workspaces").find_one({"workspace_id": workspace_id})
    return int(workspace_id), int(w["organization_id"]) if w else 0


def insert_job(job: Dict[str, Any], user_id: int = 1, workspace_id: int | None = None) -> int:
    now = utc_now()
    opportunity_type = str(job.get("opportunity_type") or "job").lower()
    if opportunity_type not in OPPORTUNITY_TYPES:
        opportunity_type = "other"
    classification = str(job.get("classification") or opportunity_type).lower()
    if classification not in OPPORTUNITY_TYPES:
        classification = "unknown"

    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    payload = {
        "title": job.get("title") or "Untitled role",
        "user_id": user_id,
        "workspace_id": scoped_workspace_id,
        "organization_id": organization_id,
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "remote_type": job.get("remote_type", ""),
        "url": job.get("url") or None,
        "source": job.get("source", "Manual"),
        "date_received": job.get("date_received", ""),
        "description": job.get("description", ""),
        "recruiter_email": job.get("recruiter_email", ""),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "deadline": job.get("deadline", ""),
        "raw_text": job.get("raw_text", ""),
        "opportunity_type": opportunity_type,
        "classification": classification,
        "classification_reason": job.get("classification_reason", ""),
        "classification_confidence": job.get("classification_confidence"),
        "opportunity_confidence": job.get("opportunity_confidence"),
        "importable": 1 if job.get("importable", True) else 0,
        "blocked_reason": job.get("blocked_reason", ""),
        "source_type": job.get("source_type", ""),
        "source_name": job.get("source_name", ""),
        "source_url": job.get("source_url", ""),
        "source_email_id": job.get("source_email_id", ""),
        "source_email_open_url": job.get("source_email_open_url", ""),
        "parent_source_id": job.get("parent_source_id", ""),
        "parent_source_title": job.get("parent_source_title", ""),
        "extracted_from": job.get("extracted_from", ""),
        "raw_source_snippet": job.get("raw_source_snippet", ""),
        "original_url": job.get("original_url", ""),
        "resolved_url": job.get("resolved_url", job.get("url") or ""),
        "content_hash": job.get("content_hash") or _content_hash(job),
        "created_at": now,
        "updated_at": now,
    }

    jobs = get_collection("jobs")
    try:
        job_id = _next_id("job_id")
        payload["job_id"] = job_id
        jobs.insert_one(payload)
        get_collection("applications").update_one({"job_id": job_id}, {"$set": {"job_id": job_id, "status": "New", "notes": "", "last_updated": now}}, upsert=True)
        add_audit_log(user_id, "opportunity.create", "job", str(job_id), {"title": payload["title"]}, workspace_id=scoped_workspace_id, organization_id=organization_id)
        return job_id
    except pymongo_errors.DuplicateKeyError:
        existing = jobs.find_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "url": payload["url"]})
        if existing:
            return int(existing["job_id"])
        raise


def _content_hash(job: dict[str, Any]) -> str:
    raw = "|".join([
        str(job.get("title") or "").strip().lower(),
        str(job.get("company") or "").strip().lower(),
        str(job.get("description") or job.get("raw_text") or "").strip().lower(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


FUZZY_DUP_THRESHOLD = 0.85

COMMON_ABBREVIATIONS = {
    "sr": "senior",
    "jr": "junior",
    "eng": "engineer",
    "dev": "developer",
    "mgr": "manager",
    "vp": "vicepresident",
    "cto": "chieftechnologyofficer",
    "ceo": "chiefexecutiveofficer",
    "cfo": "chieffinancialofficer",
    "cio": "chiefinformationofficer",
    "cmo": "chiefmarketingofficer",
    "coo": "chiefoperatingofficer",
    "svp": "seniorvicepresident",
    "evp": "executivevicepresident",
    "dir": "director",
    "dept": "department",
    "assoc": "associate",
    "asst": "assistant",
    "admin": "administrator",
    "sys": "system",
    "temp": "temporary",
}


def _normalize_for_fuzzy(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    tokens = text.split()
    tokens = [COMMON_ABBREVIATIONS.get(t, t) for t in tokens]
    text = " ".join(tokens)
    text = re.sub(r"\s+", " ", text)
    return text


def _fuzzy_match_title_company(title: str, company: str, existing_pairs: list[tuple[str, str]], threshold: float = FUZZY_DUP_THRESHOLD) -> bool:
    from difflib import SequenceMatcher
    if not title or not company:
        return False
    norm_title = _normalize_for_fuzzy(title)
    norm_company = _normalize_for_fuzzy(company)
    title_tokens = norm_title.split()
    for et, ec in existing_pairs:
        if not et or not ec:
            continue
        et_norm = _normalize_for_fuzzy(et)
        ec_norm = _normalize_for_fuzzy(ec)
        title_ratio = SequenceMatcher(None, norm_title, et_norm).ratio()
        company_ratio = SequenceMatcher(None, norm_company, ec_norm).ratio()
        if title_ratio >= threshold and company_ratio >= threshold:
            return True
        if company_ratio < threshold:
            continue
        et_tokens = et_norm.split()
        token_matches = 0
        for t in title_tokens:
            for et2 in et_tokens:
                if SequenceMatcher(None, t, et2).ratio() >= 0.75:
                    token_matches += 1
                    break
        if len(title_tokens) > 0 and token_matches / len(title_tokens) >= 0.8:
            return True
    return False


def job_exists(job: dict[str, Any], user_id: int = 1, workspace_id: int | None = None) -> bool:
    """Check if a job already exists by URL, content hash, title+company, or fuzzy title+company."""
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    query: list[dict[str, Any]] = []
    url = (job.get("url") or "").strip()
    if url:
        query.append({"user_id": user_id, "workspace_id": scoped_workspace_id, "url": url})
    title = (job.get("title") or "").strip()
    company = (job.get("company") or "").strip()
    if title and company:
        query.append({"user_id": user_id, "workspace_id": scoped_workspace_id, "title": title, "company": company})
    ch = _content_hash(job)
    query.append({"user_id": user_id, "workspace_id": scoped_workspace_id, "content_hash": ch})
    if not query:
        return False
    exact = bool(get_collection("jobs").find_one({"$or": query}))
    if exact:
        return True
    if title and company:
        existing = list(get_collection("jobs").find(
            {"user_id": user_id, "workspace_id": scoped_workspace_id},
            {"title": 1, "company": 1},
        ))
        existing_pairs = [
            (str(e.get("title") or "").strip(), str(e.get("company") or "").strip())
            for e in existing
            if e.get("title") and e.get("company")
        ]
        if _fuzzy_match_title_company(title, company, existing_pairs):
            return True
    return False


def job_url_exists(url: str, user_id: int = 1, workspace_id: int | None = None) -> bool:
    if not (url or "").strip():
        return False
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    return bool(get_collection("jobs").find_one({"user_id": user_id, "workspace_id": scoped_workspace_id, "url": url.strip()}))


def list_jobs(user_id: int = 1, workspace_id: int | None = None, content_type: str = "job") -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    filters: dict[str, Any] = {"user_id": user_id, "workspace_id": scoped_workspace_id}
    normalized_content_type = (content_type or "job").strip().lower()
    if normalized_content_type in {"job", "jobs"}:
        filters["$or"] = [
            {"classification": {"$in": list(JOB_LIKE_TYPES)}},
            {"opportunity_type": {"$in": list(JOB_LIKE_TYPES)}},
        ]
    elif normalized_content_type not in {"all", "any"}:
        filters["$or"] = [
            {"classification": normalized_content_type},
            {"opportunity_type": normalized_content_type},
        ]

    jobs = get_collection("jobs")
    cursor = jobs.find(filters).sort("updated_at", pymongo.DESCENDING)
    results = []
    for job in cursor:
        item = _job_with_id_alias(job)
        app = get_collection("applications").find_one({"job_id": item["job_id"]})
        if app:
            item["status"] = app.get("status", "")
            item["notes"] = app.get("notes", "")
        eval_doc = get_collection("evaluations").find_one({"job_id": item["job_id"]})
        if eval_doc:
            item["match_score"] = eval_doc.get("match_score")
            item["priority"] = eval_doc.get("priority")
        mat = get_collection("application_materials").find_one({"job_id": item["job_id"]})
        if mat:
            item["cover_letter"] = mat.get("cover_letter")
            item["screening_answers"] = mat.get("screening_answers")
        results.append(item)
    results.sort(key=lambda x: x.get("match_score", -1) or -1, reverse=True)
    return results


def get_job(job_id: int, user_id: int = 1, workspace_id: int | None = None) -> dict[str, Any]:
    jobs = get_collection("jobs")
    if workspace_id is None:
        job = jobs.find_one({"job_id": job_id, "user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        job = jobs.find_one({"job_id": job_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    if not job:
        return {}
    item = _job_with_id_alias(job)
    app = get_collection("applications").find_one({"job_id": job_id})
    if app:
        item["status"] = app.get("status", "")
        item["notes"] = app.get("notes", "")
    eval_doc = get_collection("evaluations").find_one({"job_id": job_id})
    if eval_doc:
        item["match_score"] = eval_doc.get("match_score")
        item["priority"] = eval_doc.get("priority")
        item["good_fit"] = eval_doc.get("good_fit")
        item["weak_areas"] = eval_doc.get("weak_areas")
        item["red_flags"] = eval_doc.get("red_flags")
    evaluation = get_evaluation(job_id, user_id)
    item["evaluation"] = evaluation or None
    return item


def delete_job(job_id: int, user_id: int = 1, workspace_id: int | None = None) -> None:
    jobs = get_collection("jobs")
    if workspace_id is None:
        job = jobs.find_one({"job_id": job_id, "user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        job = jobs.find_one({"job_id": job_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    if not job:
        return
    for table in ["evaluations", "application_materials", "applications", "reminders", "resume_reviews", "interview_prep_sessions", "recordings"]:
        get_collection(table).delete_many({"job_id": job_id})
    jobs.delete_one({"job_id": job_id, "user_id": user_id})
    if job:
        add_audit_log(user_id, "opportunity.delete", "job", str(job_id), {}, workspace_id=job.get("workspace_id"), organization_id=job.get("organization_id"))


JOB_DATA_TABLE_ORDER = [
    "evaluations", "application_materials", "applications", "reminders",
    "resume_reviews", "interview_prep_sessions", "recordings", "jobs",
]


def clear_job_data(user_id: int | None = None, *, dry_run: bool = True) -> dict[str, Any]:
    jobs_coll = get_collection("jobs")
    filter_q = {"user_id": user_id} if user_id is not None else {}
    job_ids = [int(j["job_id"]) for j in jobs_coll.find(filter_q, {"job_id": 1})]
    counts: dict[str, int] = {}

    def count_rows(table: str, where: dict | None = None) -> int:
        return get_collection(table).count_documents(where or {})

    jip = {"job_id": {"$in": job_ids}} if job_ids else {"job_id": {"$in": [-1]}}
    counts["evaluations"] = count_rows("evaluations", jip) if job_ids else 0
    counts["application_materials"] = count_rows("application_materials", jip) if job_ids else 0
    counts["applications"] = count_rows("applications", jip) if job_ids else 0
    counts["reminders"] = count_rows("reminders", jip) if job_ids else 0
    if user_id is None:
        counts["resume_reviews"] = count_rows("resume_reviews")
        counts["interview_prep_sessions"] = count_rows("interview_prep_sessions")
        counts["recordings"] = count_rows("recordings")
        counts["jobs"] = count_rows("jobs")
    else:
        uf = {"user_id": user_id}
        counts["resume_reviews"] = count_rows("resume_reviews", uf)
        counts["interview_prep_sessions"] = count_rows("interview_prep_sessions", uf)
        counts["recordings"] = count_rows("recordings", uf)
        counts["jobs"] = count_rows("jobs", uf)

    result = {
        "dry_run": dry_run,
        "user_id": user_id,
        "tables": counts,
        "total_rows": sum(counts.values()),
        "preserved": [
            "users", "profile", "user_sessions", "password_reset_tokens",
            "integration_settings", "provider_configs", "automation_preferences",
            "organizations", "workspaces", "workspace_members",
        ],
    }
    if dry_run:
        return result

    if job_ids:
        jip = {"job_id": {"$in": job_ids}}
        get_collection("evaluations").delete_many(jip)
        get_collection("application_materials").delete_many(jip)
        get_collection("applications").delete_many(jip)
        get_collection("reminders").delete_many(jip)
    if user_id is None:
        for t in ["resume_reviews", "interview_prep_sessions", "recordings", "jobs"]:
            get_collection(t).delete_many({})
    else:
        uf = {"user_id": user_id}
        get_collection("resume_reviews").delete_many(uf)
        get_collection("interview_prep_sessions").delete_many(uf)
        get_collection("recordings").delete_many(uf)
        get_collection("jobs").delete_many(uf)
    result["deleted"] = counts
    return result


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


def _safe_json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


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


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def save_evaluation(job_id: int, evaluation: Dict[str, Any], user_id: int = 1) -> None:
    now = utc_now()
    if not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    values = {
        "job_id": job_id,
        "match_score": int(evaluation.get("match_score", 0)),
        "priority": evaluation.get("priority", "Low"),
        "skill_match": int(evaluation.get("skill_match", 0)),
        "title_match": int(evaluation.get("title_match", 0)),
        "seniority_match": int(evaluation.get("seniority_match", 0)),
        "location_match": int(evaluation.get("location_match", 0)),
        "salary_match": int(evaluation.get("salary_match", 0)),
        "industry_match": int(evaluation.get("industry_match", 0)),
        "authorization_match": int(evaluation.get("authorization_match", 0)),
        "deal_breaker_penalty": int(evaluation.get("deal_breaker_penalty", 0)),
        "good_fit": _as_text(evaluation.get("good_fit", "")),
        "weak_areas": _as_text(evaluation.get("weak_areas", "")),
        "red_flags": _as_text(evaluation.get("red_flags", "")),
        "opportunity_type": evaluation.get("opportunity_type", "job"),
        "prize_value_score": evaluation.get("prize_value_score"),
        "tech_alignment_score": evaluation.get("tech_alignment_score"),
        "webinar_relevance_score": evaluation.get("webinar_relevance_score") or evaluation.get("topic_relevance"),
        "generated_at": now,
    }
    get_collection("evaluations").update_one({"job_id": job_id}, {"$set": values}, upsert=True)


def get_evaluation(job_id: int, user_id: int = 1) -> dict[str, Any]:
    doc = get_collection("evaluations").find_one({"job_id": job_id})
    if doc:
        job = get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id})
        if job:
            return _strip_id(doc)
    return {}


def cleanup_non_opportunity_records(user_id: int = 1, workspace_id: int | None = None) -> dict[str, Any]:
    from job_assistant.services.opportunity_classifier import annotate_opportunity

    updated = 0
    evaluations_removed = 0
    inspected = 0
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    jobs = get_collection("jobs")
    cursor = jobs.find({
        "user_id": user_id, "workspace_id": scoped_workspace_id,
        "$or": [
            {"source": {"$regex": "gmail", "$options": "i"}},
            {"title": {"$regex": "^subject:", "$options": "i"}},
            {"company": {"$in": ["unknown company", "unknown"]}},
            {"$or": [
                {"description": {"$regex": "newsletter", "$options": "i"}},
                {"raw_text": {"$regex": "newsletter", "$options": "i"}},
            ]},
            {"url": {"$regex": "medium\\.com", "$options": "i"}},
            {"url": {"$regex": "sendgrid", "$options": "i"}},
        ],
    })
    for job_doc in cursor:
        inspected += 1
        item = _strip_id(job_doc)
        annotated = annotate_opportunity(item)
        if annotated.get("importable"):
            continue
        now = utc_now()
        jobs.update_one({"job_id": item["job_id"]}, {"$set": {
            "classification": annotated.get("classification") or "unknown",
            "classification_reason": annotated.get("classification_reason") or "",
            "classification_confidence": annotated.get("classification_confidence") or 0,
            "opportunity_confidence": annotated.get("opportunity_confidence") or 0,
            "importable": 0,
            "blocked_reason": annotated.get("blocked_reason") or "Non-opportunity content rejected by classifier.",
            "updated_at": now,
        }})
        get_collection("applications").update_one(
            {"job_id": item["job_id"]},
            {"$set": {"status": "Non-Opportunity", "notes": annotated.get("blocked_reason") or annotated.get("classification_reason") or "", "last_updated": now}},
            upsert=True,
        )
        result = get_collection("evaluations").delete_one({"job_id": item["job_id"]})
        evaluations_removed += result.deleted_count
        updated += 1
    return {"inspected": inspected, "updated": updated, "evaluations_removed": evaluations_removed}


def save_materials(job_id: int, materials: Dict[str, Any], user_id: int = 1) -> None:
    now = utc_now()
    if not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    values = {
        "job_id": job_id,
        "professional_summary": _as_text(materials.get("professional_summary", "")),
        "cover_letter": _as_text(materials.get("cover_letter", "")),
        "resume_bullets": _as_text(materials.get("resume_bullets", "")),
        "screening_answers": _as_text(materials.get("screening_answers", "")),
        "linkedin_message": _as_text(materials.get("linkedin_message", "")),
        "why_fit": _as_text(materials.get("why_fit", "")),
        "updated_at": now,
    }
    get_collection("application_materials").update_one({"job_id": job_id}, {"$set": values}, upsert=True)


def get_materials(job_id: int, user_id: int = 1) -> dict[str, Any]:
    doc = get_collection("application_materials").find_one({"job_id": job_id})
    if doc:
        if get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
            return _strip_id(doc)
    return {}


def update_status(job_id: int, status: str, notes: str = "", user_id: int = 1) -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    if not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    get_collection("applications").update_one(
        {"job_id": job_id},
        {"$set": {"status": status, "notes": notes, "last_updated": utc_now()}},
        upsert=True,
    )


def save_resume_review(user_id: int, review: Dict[str, Any], job_id: int | None = None) -> dict[str, Any]:
    now = utc_now()
    if job_id and not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    rid = _next_id("resume_review_id")
    doc = {"resume_review_id": rid, "user_id": user_id, "job_id": job_id, "review_json": json.dumps(review), "created_at": now}
    get_collection("resume_reviews").insert_one(doc)
    review["id"] = rid
    review["job_id"] = job_id
    review["created_at"] = now
    return review


def list_resume_reviews(user_id: int, job_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"user_id": user_id}
    if job_id is not None:
        q["job_id"] = job_id
    docs = get_collection("resume_reviews").find(q).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    output = []
    for doc in docs:
        item = json.loads(doc.get("review_json") or "{}")
        item.update({"id": doc["resume_review_id"], "job_id": doc.get("job_id"), "created_at": doc.get("created_at")})
        output.append(item)
    return output


def save_interview_prep(user_id: int, job_id: int, prep: Dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    if not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    pid = _next_id("interview_prep_id")
    doc = {"interview_prep_id": pid, "user_id": user_id, "job_id": job_id, "prep_json": json.dumps(prep), "created_at": now}
    get_collection("interview_prep_sessions").insert_one(doc)
    prep["id"] = pid
    prep["job_id"] = job_id
    prep["created_at"] = now
    return prep


def list_interview_prep(user_id: int, job_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"user_id": user_id}
    if job_id is not None:
        q["job_id"] = job_id
    docs = get_collection("interview_prep_sessions").find(q).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    output = []
    for doc in docs:
        item = json.loads(doc.get("prep_json") or "{}")
        item.update({"id": doc["interview_prep_id"], "job_id": doc.get("job_id"), "created_at": doc.get("created_at")})
        output.append(item)
    return output


def save_recording(user_id: int, recording: Dict[str, Any], job_id: int | None = None) -> dict[str, Any]:
    now = utc_now()
    if job_id and not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    rid = _next_id("recording_id")
    doc = {
        "recording_id": rid, "user_id": user_id, "job_id": job_id,
        "title": recording.get("title", "Interview practice recording"),
        "mime_type": recording.get("mime_type", "audio/webm"),
        "data_url": recording.get("data_url", ""),
        "duration_ms": int(recording.get("duration_ms") or 0),
        "created_at": now,
        "interview_prep_session_id": recording.get("interview_prep_session_id"),
        "original_filename": recording.get("original_filename", ""),
        "stored_path": recording.get("stored_path", ""),
        "playback_url": recording.get("playback_url", ""),
        "file_size": int(recording.get("file_size") or 0),
        "storage_type": recording.get("storage_type", ""),
    }
    get_collection("recordings").insert_one(doc)
    return {"id": rid, "job_id": job_id, "created_at": now, **recording}


def list_recordings(user_id: int, job_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"user_id": user_id}
    if job_id is not None:
        q["job_id"] = job_id
    docs = get_collection("recordings").find(q).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    output = []
    for doc in docs:
        item = _strip_id(doc)
        if not item.get("playback_url") and item.get("data_url"):
            item["playback_url"] = item["data_url"]
        output.append(item)
    return output


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


def create_reminder(job_id: int, kind: str, remind_at: str, note: str, user_id: int = 1) -> None:
    if not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    rid = _next_id("reminder_id")
    get_collection("reminders").insert_one({
        "reminder_id": rid, "job_id": job_id, "kind": kind,
        "remind_at": remind_at, "note": note, "created_at": utc_now(),
    })


def create_followup_reminders(after_days: int = 7) -> int:
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, after_days))).isoformat(timespec="seconds")
    now = utc_now()
    apps = get_collection("applications").find({"status": "Applied", "last_updated": {"$lte": cutoff}})
    created = 0
    for app in apps:
        job_id = int(app["job_id"])
        existing = get_collection("reminders").find_one({"job_id": job_id, "kind": "followup", "done": 0})
        if existing:
            continue
        job = get_collection("jobs").find_one({"job_id": job_id})
        company = (job.get("company") or "this company").strip() or "this company" if job else "this company"
        note = f"No response from {company} in {after_days} days — consider following up."
        rid = _next_id("reminder_id")
        get_collection("reminders").insert_one({"reminder_id": rid, "job_id": job_id, "kind": "followup", "remind_at": now, "note": note, "created_at": now, "done": 0})
        created += 1
    return created


def due_reminders(user_id: int = 1) -> list[dict[str, Any]]:
    now = utc_now()
    pipeline = [
        {"$match": {"done": 0, "remind_at": {"$lte": now}}},
        {"$lookup": {"from": "jobs", "localField": "job_id", "foreignField": "job_id", "as": "job"}},
        {"$unwind": {"path": "$job", "preserveNullAndEmptyArrays": True}},
        {"$match": {"job.user_id": user_id}},
        {"$sort": {"remind_at": pymongo.ASCENDING}},
    ]
    docs = get_collection("reminders").aggregate(pipeline)
    results = []
    for doc in docs:
        item = _strip_id(doc)
        item["title"] = doc.get("job", {}).get("title")
        item["company"] = doc.get("job", {}).get("company")
        results.append(item)
    return results


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session_token(user_id: int, days: int = 30) -> str:
    token = secrets.token_urlsafe(48)
    now = utc_now()
    from datetime import datetime, timezone, timedelta
    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
    get_collection("user_sessions").insert_one({
        "user_id": user_id, "token_hash": _token_hash(token),
        "created_at": now, "expires_at": expires_at,
    })
    return token


def get_user_by_session_token(token: str) -> dict[str, Any]:
    if not token:
        return {}
    doc = get_collection("user_sessions").find_one({
        "token_hash": _token_hash(token), "revoked_at": None,
        "expires_at": {"$gt": utc_now()},
    })
    if not doc:
        return {}
    user = get_collection("users").find_one({"user_id": doc["user_id"], "is_active": 1})
    return _user_with_id_alias(user) if user else {}


def revoke_session_token(token: str) -> None:
    if not token:
        return
    get_collection("user_sessions").update_one(
        {"token_hash": _token_hash(token)},
        {"$set": {"revoked_at": utc_now()}},
    )


def create_password_reset_token(user_id: int, token: str, expires_at: str, ip_address: str = "", user_agent: str = "") -> int:
    now = utc_now()
    tid = _next_id("password_reset_token_id")
    get_collection("password_reset_tokens").insert_one({
        "password_reset_token_id": tid, "user_id": user_id,
        "token_hash": _token_hash(token), "created_at": now,
        "expires_at": expires_at, "ip_address": ip_address,
        "user_agent": user_agent,
    })
    return tid


def get_password_reset_token(token: str) -> dict[str, Any]:
    if not token:
        return {}
    now = utc_now()
    token_hash = _token_hash(token)
    doc = get_collection("password_reset_tokens").find_one({
        "token_hash": token_hash, "consumed_at": None,
        "expires_at": {"$gt": now},
    })
    if not doc:
        return {}
    user = get_collection("users").find_one({"user_id": doc["user_id"], "is_active": 1})
    item = _strip_id(doc)
    if user:
        item["email"] = user.get("email")
        item["user_email"] = user.get("email")
    return item


def consume_password_reset_token(token_id: int) -> bool:
    result = get_collection("password_reset_tokens").update_one(
        {"password_reset_token_id": token_id, "consumed_at": None},
        {"$set": {"consumed_at": utc_now()}},
    )
    return result.modified_count == 1


def update_user_password(user_id: int, password_hash: str) -> None:
    get_collection("users").update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": password_hash, "updated_at": utc_now()}},
    )


def revoke_user_sessions(user_id: int) -> None:
    get_collection("user_sessions").update_many(
        {"user_id": user_id, "revoked_at": None},
        {"$set": {"revoked_at": utc_now()}},
    )


def get_automation_preferences(user_id: int) -> dict[str, Any]:
    doc = get_collection("automation_preferences").find_one({"user_id": user_id})
    if doc:
        data = _strip_id(doc)
    else:
        data = {
            "user_id": user_id, "enabled": 0, "gmail_enabled": 1,
            "public_sources_enabled": 1, "linkedin_api_enabled": 0,
            "score_new": 1, "generate_materials": 0,
            "gmail_interval_minutes": 30, "public_interval_hours": 6,
            "linkedin_interval_hours": 6, "daily_summary_hour": 8,
            "notify_in_app": 1, "min_score_for_materials": 70,
            "updated_at": utc_now(),
        }
    for key in ["enabled", "gmail_enabled", "public_sources_enabled", "linkedin_api_enabled", "score_new", "generate_materials", "notify_in_app"]:
        data[key] = bool(data.get(key))
    return data


def save_automation_preferences(user_id: int, prefs: Dict[str, Any]) -> None:
    current = get_automation_preferences(user_id)
    current.update(prefs or {})
    fields = [
        "enabled", "gmail_enabled", "public_sources_enabled", "linkedin_api_enabled",
        "score_new", "generate_materials", "gmail_interval_minutes",
        "public_interval_hours", "linkedin_interval_hours", "daily_summary_hour",
        "notify_in_app", "min_score_for_materials",
    ]
    values = {k: int(current[k]) if isinstance(current[k], bool) else current[k] for k in fields}
    values["updated_at"] = utc_now()
    get_collection("automation_preferences").update_one(
        {"user_id": user_id},
        {"$set": values},
        upsert=True,
    )


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


def add_activity_event(user_id: int, title: str, message: str = "", level: str = "info", metadata: Dict[str, Any] | None = None) -> None:
    eid = _next_id("activity_event_id")
    get_collection("activity_events").insert_one({
        "activity_event_id": eid, "user_id": user_id, "level": level,
        "title": title, "message": message,
        "metadata_json": json.dumps(metadata or {}),
        "created_at": utc_now(), "read_at": None,
    })


def list_activity_events(user_id: int, limit: int = 50, unread_only: bool = False) -> list[dict[str, Any]]:
    q: dict[str, Any] = {"user_id": user_id}
    if unread_only:
        q["read_at"] = None
    docs = get_collection("activity_events").find(q).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def mark_activity_read(user_id: int) -> None:
    get_collection("activity_events").update_many(
        {"user_id": user_id, "read_at": None},
        {"$set": {"read_at": utc_now()}},
    )


FEEDBACK_CATEGORIES = [
    "Bug Report", "Feature Request", "AI Quality Issue", "UI/UX Feedback",
    "Provider/API Problem", "Performance Issue", "Security Concern",
    "Automation Failure", "Integration Request", "General Suggestion",
]
FEEDBACK_SEVERITIES = ["low", "medium", "high", "critical"]
FEEDBACK_STATUSES = ["open", "triaged", "in_review", "planned", "in_progress", "resolved", "closed", "duplicate", "wont_fix"]


def create_feedback(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    category = str(payload.get("category") or "General Suggestion").strip()
    if category not in FEEDBACK_CATEGORIES:
        category = "General Suggestion"
    severity = str(payload.get("severity") or "medium").strip().lower()
    if severity not in FEEDBACK_SEVERITIES:
        severity = "medium"
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    if not title or not description:
        raise ValueError("Feedback title and description are required")
    now = utc_now()
    metadata = payload.get("metadata") or {}
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id or payload.get("workspace_id"))
    fid = _next_id("feedback_id")
    get_collection("feedback").insert_one({
        "feedback_id": fid, "user_id": user_id, "workspace_id": scoped_workspace_id,
        "organization_id": organization_id, "category": category, "title": title,
        "description": description, "severity": severity,
        "status": str(payload.get("status") or "open"),
        "attachment_url": str(payload.get("attachment_url") or ""),
        "page_url": str(payload.get("page_url") or ""),
        "user_agent": str(payload.get("user_agent") or ""),
        "app_version": str(payload.get("app_version") or ""),
        "metadata_json": json.dumps(metadata), "created_at": now, "updated_at": now,
    })
    add_audit_log(user_id, "feedback.create", "feedback", str(fid), {"category": category, "severity": severity}, workspace_id=scoped_workspace_id, organization_id=organization_id)
    return fid


def list_feedback(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("feedback").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def get_feedback(feedback_id: int, user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    if workspace_id is None:
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    return _strip_id(doc) if doc else {}


def update_feedback_status(feedback_id: int, user_id: int, status: str, workspace_id: int | None = None) -> None:
    status = str(status or "").strip().lower()
    if status not in FEEDBACK_STATUSES:
        raise ValueError(f"Invalid feedback status: {status}")
    if workspace_id is None:
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        doc = get_collection("feedback").find_one({"feedback_id": feedback_id, "user_id": user_id, "workspace_id": scoped_workspace_id})
    if not doc:
        raise ValueError("Feedback not found")
    get_collection("feedback").update_one(
        {"feedback_id": feedback_id, "user_id": user_id},
        {"$set": {"status": status, "updated_at": utc_now()}},
    )
    add_audit_log(user_id, "feedback.update_status", "feedback", str(feedback_id), {"status": status}, workspace_id=doc.get("workspace_id"), organization_id=doc.get("organization_id"))


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


def list_audit_logs(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    if workspace_id is None:
        docs = get_collection("audit_logs").find({"user_id": user_id})
    else:
        scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
        docs = get_collection("audit_logs").find({"user_id": user_id, "workspace_id": scoped_workspace_id})
    docs = docs.sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def db_health() -> dict[str, Any]:
    started = utc_now()
    col = get_collection("users")
    users_count = col.count_documents({})
    feedback_count = get_collection("feedback").count_documents({})
    usage_count = get_collection("usage_counters").count_documents({})
    return {"status": "ok", "checked_at": started, "users": users_count, "feedback": feedback_count, "usage_counters": usage_count}


def storage_health() -> dict[str, Any]:
    return {"status": "ok", "database": "mongodb", "database_url": MONGO_URL}


def increment_usage_counter(
    *, resource_type: str, window_start: str, window_end: str,
    user_id: int | None = None, ip_address: str = "",
) -> int:
    now = utc_now()
    counter_user_id = int(user_id) if user_id is not None else -1
    col = get_collection("usage_counters")
    col.delete_many({"window_end": {"$lt": now}})
    try:
        col.update_one(
            {"user_id": counter_user_id, "ip_address": ip_address or "", "resource_type": resource_type, "window_start": window_start},
            {"$inc": {"count": 1}, "$set": {"window_end": window_end, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except pymongo_errors.DuplicateKeyError:
        col.update_one(
            {"user_id": counter_user_id, "ip_address": ip_address or "", "resource_type": resource_type, "window_start": window_start},
            {"$inc": {"count": 1}, "$set": {"window_end": window_end, "updated_at": now}},
        )
    doc = col.find_one({"user_id": counter_user_id, "ip_address": ip_address or "", "resource_type": resource_type, "window_start": window_start})
    return int(doc["count"]) if doc else 1


def usage_summary(user_id: int | None = None) -> list[dict[str, Any]]:
    now = utc_now()
    q: dict[str, Any] = {"window_end": {"$gte": now}}
    if user_id is not None:
        q["user_id"] = user_id
    pipeline = [
        {"$match": q},
        {"$group": {
            "_id": "$resource_type",
            "count": {"$sum": "$count"},
            "window_start": {"$min": "$window_start"},
            "window_end": {"$max": "$window_end"},
        }},
        {"$sort": {"_id": pymongo.ASCENDING}},
    ]
    results = []
    for doc in get_collection("usage_counters").aggregate(pipeline):
        results.append({
            "resource_type": doc["_id"],
            "count": doc["count"],
            "window_start": doc["window_start"],
            "window_end": doc["window_end"],
        })
    return results


def log_ai_generation(
    user_id: int | None, *, provider: str = "", model: str = "",
    task_type: str = "general", prompt_version: str = "", prompt_hash: str = "",
    input_tokens: int = 0, output_tokens: int = 0, estimated_cost: float = 0.0,
    latency_ms: int | None = None, status: str = "unknown",
    error_message: str = "", workspace_id: int | None = None,
) -> int:
    scoped_workspace_id = None
    organization_id = None
    if user_id:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    gid = _next_id("ai_generation_id")
    get_collection("ai_generations").insert_one({
        "ai_generation_id": gid, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "provider": provider, "model": model, "task_type": task_type,
        "prompt_version": prompt_version, "prompt_hash": prompt_hash,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "estimated_cost": float(estimated_cost or 0),
        "latency_ms": latency_ms, "status": status,
        "error_message": error_message, "created_at": utc_now(),
    })
    return gid


def record_score_feedback(user_id: int, job_id: int, signal: str, workspace_id: int | None = None) -> int:
    signal = (signal or "").strip().lower()
    if signal not in ("relevant", "irrelevant"):
        raise ValueError("signal must be 'relevant' or 'irrelevant'")
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    sfid = _next_id("score_feedback_id")
    get_collection("score_feedback").insert_one({
        "score_feedback_id": sfid, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "job_id": job_id,
        "signal": signal, "created_at": utc_now(),
    })
    return sfid


def recent_score_feedback(user_id: int, limit: int = 10, workspace_id: int | None = None) -> list[dict[str, Any]]:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort": {"_id": pymongo.DESCENDING}},
        {"$limit": max(1, min(int(limit), 50))},
        {"$lookup": {"from": "jobs", "localField": "job_id", "foreignField": "job_id", "as": "job"}},
        {"$unwind": {"path": "$job", "preserveNullAndEmptyArrays": True}},
        {"$project": {"signal": 1, "created_at": 1, "title": "$job.title", "company": "$job.company"}},
    ]
    return list(get_collection("score_feedback").aggregate(pipeline))


def count_ai_generations_today(user_id: int) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    count = get_collection("ai_generations").count_documents({
        "user_id": user_id,
        "created_at": {"$regex": f"^{today}"},
        "provider": {"$nin": [None, "", "none"]},
    })
    return count


def list_ai_generations(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("ai_generations").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def ai_usage_detailed(user_id: int) -> dict[str, Any]:
    """Aggregated usage breakdown: today, this week, this month, and daily history."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    thirty_days_ago = (now - timedelta(days=30)).isoformat(timespec="seconds")

    def _agg(start: str) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"user_id": user_id, "created_at": {"$gte": start}}},
            {"$group": {
                "_id": "$task_type",
                "calls": {"$sum": 1},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "estimated_cost": {"$sum": "$estimated_cost"},
                "latency_ms": {"$avg": "$latency_ms"},
            }},
            {"$sort": {"calls": pymongo.DESCENDING}},
        ]
        results = []
        for doc in get_collection("ai_generations").aggregate(pipeline):
            results.append({
                "task_type": doc["_id"] or "unknown",
                "calls": doc["calls"],
                "input_tokens": doc["input_tokens"],
                "output_tokens": doc["output_tokens"],
                "estimated_cost": round(doc["estimated_cost"], 6),
                "avg_latency_ms": int(doc["latency_ms"] or 0),
            })
        return results

    def _daily() -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"user_id": user_id, "created_at": {"$gte": thirty_days_ago}}},
            {"$project": {"day": {"$substr": ["$created_at", 0, 10]}, "input_tokens": 1, "output_tokens": 1, "estimated_cost": 1, "status": 1}},
            {"$group": {
                "_id": "$day",
                "calls": {"$sum": 1},
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "estimated_cost": {"$sum": "$estimated_cost"},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            }},
            {"$sort": {"_id": pymongo.DESCENDING}},
        ]
        results = []
        for doc in get_collection("ai_generations").aggregate(pipeline):
            results.append({
                "date": doc["_id"],
                "calls": doc["calls"],
                "input_tokens": doc["input_tokens"],
                "output_tokens": doc["output_tokens"],
                "estimated_cost": round(doc["estimated_cost"], 6),
                "failed": doc["failed"],
            })
        return results

    today_agg = _agg(today_start)
    total_today = {"calls": sum(r["calls"] for r in today_agg), "input_tokens": sum(r["input_tokens"] for r in today_agg), "output_tokens": sum(r["output_tokens"] for r in today_agg), "estimated_cost": round(sum(r["estimated_cost"] for r in today_agg), 6)}
    week_agg = _agg(week_start)
    total_week = {"calls": sum(r["calls"] for r in week_agg), "input_tokens": sum(r["input_tokens"] for r in week_agg), "output_tokens": sum(r["output_tokens"] for r in week_agg), "estimated_cost": round(sum(r["estimated_cost"] for r in week_agg), 6)}
    month_agg = _agg(month_start)
    total_month = {"calls": sum(r["calls"] for r in month_agg), "input_tokens": sum(r["input_tokens"] for r in month_agg), "output_tokens": sum(r["output_tokens"] for r in month_agg), "estimated_cost": round(sum(r["estimated_cost"] for r in month_agg), 6)}

    return {
        "today": {"total": total_today, "by_task_type": today_agg},
        "this_week": {"total": total_week, "by_task_type": week_agg},
        "this_month": {"total": total_month, "by_task_type": month_agg},
        "daily_history": _daily(),
    }


def get_rate_limit_status() -> list[dict[str, Any]]:
    """Return current usage vs limits for all rate-limited resource types."""
    now = utc_now()
    from datetime import datetime, timezone, timedelta
    from job_assistant.config import settings
    limits = [
        ("ai_generation", settings.rate_limit_ai_per_hour, 60),
        ("sse_chat", settings.rate_limit_sse_per_minute, 1),
        ("feedback", settings.rate_limit_feedback_per_hour, 60),
        ("publishing", settings.rate_limit_publish_per_hour, 60),
        ("api_request", settings.rate_limit_per_minute, 1),
    ]
    results = []
    for resource_type, limit, window_minutes in limits:
        if limit <= 0:
            continue
        if window_minutes >= 60:
            hours = window_minutes // 60
            start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            window_start = start.isoformat(timespec="seconds")
            window_end = (start + timedelta(hours=hours)).isoformat(timespec="seconds")
        else:
            start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            window_start = start.isoformat(timespec="seconds")
            window_end = (start + timedelta(minutes=window_minutes)).isoformat(timespec="seconds")
        docs = get_collection("usage_counters").find({"resource_type": resource_type, "window_start": window_start})
        count = sum(int(d.get("count", 0)) for d in docs)
        results.append({
            "resource_type": resource_type,
            "limit": limit,
            "used": count,
            "remaining": max(0, limit - count),
            "window_start": window_start,
            "window_end": window_end,
        })
    return results


def upsert_prompt_version(name: str, version: str, template: str, description: str = "", is_active: bool = True) -> None:
    now = utc_now()
    get_collection("prompt_versions").update_one(
        {"name": name, "version": version},
        {"$set": {"description": description, "template": template, "is_active": 1 if is_active else 0, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


def list_prompt_versions(limit: int = 100) -> list[dict[str, Any]]:
    docs = get_collection("prompt_versions").find().sort([("name", pymongo.ASCENDING), ("version", pymongo.ASCENDING)]).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


def get_active_prompt(name: str) -> str:
    """Return the template text of the active prompt version for a given name,
    or empty string if none is configured."""
    doc = get_collection("prompt_versions").find_one(
        {"name": name, "is_active": 1},
        sort=[("version", pymongo.DESCENDING)],
    )
    if doc:
        return doc.get("template", "")
    return ""


def delete_prompt_version(name: str, version: str) -> bool:
    result = get_collection("prompt_versions").delete_one({"name": name, "version": version})
    return result.deleted_count > 0


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


# ---------------------------------------------------------------------------
# Agent memory – persistent key-value facts remembered across conversations
# ---------------------------------------------------------------------------
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
    """Return a compact string of memory facts for injection into system prompts."""
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


def create_automation_rule(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    now = utc_now()
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id or payload.get("workspace_id"))
    rid = _next_id("automation_rule_id")
    get_collection("automation_rules").insert_one({
        "automation_rule_id": rid, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "name": str(payload.get("name") or "Automation rule"),
        "trigger_event": str(payload.get("trigger_event") or "manual"),
        "action_type": str(payload.get("action_type") or "notify"),
        "conditions_json": json.dumps(payload.get("conditions") or {}),
        "action_config_json": json.dumps(payload.get("action_config") or {}),
        "is_active": 1 if payload.get("is_active", True) else 0,
        "human_approval_required": 1 if payload.get("human_approval_required", True) else 0,
        "created_at": now, "updated_at": now,
    })
    add_audit_log(user_id, "automation_rule.create", "automation_rule", str(rid), {"trigger_event": payload.get("trigger_event"), "action_type": payload.get("action_type")}, workspace_id=scoped_workspace_id, organization_id=organization_id)
    return rid


def list_automation_rules(user_id: int, include_inactive: bool = False, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    q: dict[str, Any] = {"user_id": user_id, "workspace_id": scoped_workspace_id}
    if not include_inactive:
        q["is_active"] = 1
    docs = get_collection("automation_rules").find(q).sort("created_at", pymongo.DESCENDING)
    out = []
    for doc in docs:
        item = _strip_id(doc)
        item["conditions"] = _safe_json_loads(item.pop("conditions_json", "{}"), {})
        item["action_config"] = _safe_json_loads(item.pop("action_config_json", "{}"), {})
        item["is_active"] = bool(item.get("is_active"))
        item["human_approval_required"] = bool(item.get("human_approval_required"))
        out.append(item)
    return out


def update_automation_rule(rule_id: int, user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> None:
    current = next((r for r in list_automation_rules(user_id, include_inactive=True, workspace_id=workspace_id) if int(r["automation_rule_id"]) == int(rule_id)), None)
    if not current:
        raise ValueError("Automation rule not found")
    merged = {**current, **(payload or {})}
    get_collection("automation_rules").update_one(
        {"automation_rule_id": rule_id, "user_id": user_id, "workspace_id": current["workspace_id"]},
        {"$set": {
            "name": str(merged.get("name") or current["name"]),
            "trigger_event": str(merged.get("trigger_event") or current["trigger_event"]),
            "action_type": str(merged.get("action_type") or current["action_type"]),
            "conditions_json": json.dumps(merged.get("conditions") or {}),
            "action_config_json": json.dumps(merged.get("action_config") or {}),
            "is_active": 1 if merged.get("is_active", True) else 0,
            "human_approval_required": 1 if merged.get("human_approval_required", True) else 0,
            "updated_at": utc_now(),
        }},
    )
    add_audit_log(user_id, "automation_rule.update", "automation_rule", str(rule_id), {}, workspace_id=current["workspace_id"], organization_id=current.get("organization_id"))


def delete_automation_rule(rule_id: int, user_id: int, workspace_id: int | None = None) -> None:
    current = next((r for r in list_automation_rules(user_id, include_inactive=True, workspace_id=workspace_id) if int(r["automation_rule_id"]) == int(rule_id)), None)
    if current:
        get_collection("automation_rules").delete_one({"automation_rule_id": rule_id, "user_id": user_id, "workspace_id": current["workspace_id"]})
        add_audit_log(user_id, "automation_rule.delete", "automation_rule", str(rule_id), {}, workspace_id=current["workspace_id"], organization_id=current.get("organization_id"))


def create_automation_run(user_id: int, trigger_event: str, input_payload: Dict[str, Any] | None = None, rule_id: int | None = None, status: str = "pending", workspace_id: int | None = None) -> int:
    scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    rid = _next_id("automation_run_id")
    get_collection("automation_runs").insert_one({
        "automation_run_id": rid, "rule_id": rule_id, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "status": status, "trigger_event": trigger_event,
        "input_payload": json.dumps(input_payload or {}),
        "created_at": utc_now(),
    })
    return rid


def update_automation_run(run_id: int, user_id: int, *, status: str, output_payload: Dict[str, Any] | None = None, error_message: str = "") -> None:
    now = utc_now()
    completed = now if status in {"completed", "failed", "cancelled", "requires_approval"} else None
    update: dict[str, Any] = {
        "status": status, "output_payload": json.dumps(output_payload or {}),
        "error_message": error_message, "updated_at": now,
    }
    if completed:
        update["completed_at"] = completed
    get_collection("automation_runs").update_one(
        {"automation_run_id": run_id, "user_id": user_id},
        {"$set": update, "$setOnInsert": {"started_at": now}},
    )


def list_automation_runs(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("automation_runs").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    out = []
    for doc in docs:
        item = _strip_id(doc)
        item["input_payload"] = _safe_json_loads(item.get("input_payload"), {})
        item["output_payload"] = _safe_json_loads(item.get("output_payload"), {})
        out.append(item)
    return out


def add_automation_error(user_id: int | None, run_id: int | None, error_message: str, error_type: str = "runtime", metadata: Dict[str, Any] | None = None, workspace_id: int | None = None) -> None:
    scoped_workspace_id = None
    organization_id = None
    if run_id:
        run = get_collection("automation_runs").find_one({"automation_run_id": run_id})
        if run:
            scoped_workspace_id, organization_id = run.get("workspace_id"), run.get("organization_id")
    elif user_id:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(user_id, workspace_id)
    aid = _next_id("automation_error_id")
    get_collection("automation_errors").insert_one({
        "automation_error_id": aid, "run_id": run_id, "user_id": user_id,
        "workspace_id": scoped_workspace_id, "organization_id": organization_id,
        "error_type": error_type, "error_message": error_message,
        "metadata_json": json.dumps(metadata or {}),
        "created_at": utc_now(),
    })


def list_automation_errors(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    scoped_workspace_id, _ = _workspace_scope_for_user(user_id, workspace_id)
    docs = get_collection("automation_errors").find({"user_id": user_id, "workspace_id": scoped_workspace_id}).sort("created_at", pymongo.DESCENDING).limit(max(1, min(int(limit), 500)))
    return [_strip_id(d) for d in docs]


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


def delete_user_data(user_id: int) -> None:
    job_ids = [int(j["job_id"]) for j in get_collection("jobs").find({"user_id": user_id}, {"job_id": 1})]
    if job_ids:
        jip = {"job_id": {"$in": job_ids}}
        get_collection("reminders").delete_many(jip)
        get_collection("application_materials").delete_many(jip)
        get_collection("evaluations").delete_many(jip)
        get_collection("applications").delete_many(jip)
        get_collection("jobs").delete_many(jip)
    for coll in ["profiles", "integration_settings", "automation_preferences",
                 "activity_events", "feedback", "audit_logs", "ai_generations",
                 "automation_errors", "automation_runs", "automation_rules",
                 "resume_reviews", "interview_prep_sessions", "recordings",
                 "gmail_messages"]:
        get_collection(coll).delete_many({"user_id": user_id})


def delete_all_data(user_id: int = 1) -> None:
    delete_user_data(user_id)


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
    docs = get_collection("roles").find().sort([("$expr", pymongo.ASCENDING)])
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
    can_manage = user_has_permission(user_id, workspace_id, "workspace:manage")
    if not user_has_permission(user_id, workspace_id, "member:read") and not can_manage:
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


def needs_seed() -> bool:
    return get_collection("users").count_documents({}) == 0


def seed_demo_data() -> None:
    from job_assistant.auth import hash_password

    DEMO_EMAIL = "demo@example.com"
    DEMO_PASSWORD = "DemoPass123!"
    DEMO_NAME = "Demo Candidate"

    DEMO_PROFILE = {
        "full_name": DEMO_NAME,
        "email": DEMO_EMAIL,
        "cv_text": (
            "Senior backend engineer with 7 years building Python/FastAPI services, "
            "React/TypeScript frontends, and Postgres/SQLite data layers. Led API "
            "platform work, mentored engineers, and shipped CI/CD on AWS."
        ),
        "target_roles": "Senior Backend Engineer, Platform Engineer",
        "preferred_role": "Senior Backend Engineer",
        "industries": "SaaS, Fintech, Developer Tools",
        "locations": "Remote, London",
        "country": "United Kingdom",
        "remote_preference": "remote",
        "salary_expectations": "90000-120000 GBP",
        "work_authorization": "UK citizen",
        "years_experience": "7",
        "skills": "Python, FastAPI, React, TypeScript, SQL, Postgres, AWS, Docker, CI/CD",
        "deal_breakers": "No on-site only roles, no unpaid work",
    }

    DEMO_JOBS = [
        (
            {
                "title": "Senior Backend Engineer",
                "company": "Northwind Labs",
                "location": "Remote (UK)", "remote_type": "remote",
                "url": "https://jobs.example.com/northwind/senior-backend-engineer",
                "source": "Seed", "salary_min": 95000, "salary_max": 120000,
                "opportunity_type": "job", "classification": "job", "importable": True,
                "description": (
                    "We are hiring a Senior Backend Engineer to own our FastAPI services. "
                    "Responsibilities include API design, Postgres data modelling, and CI/CD. "
                    "Requirements: 5+ years Python, strong testing discipline, AWS experience. "
                    "Salary 95k-120k. Apply now."
                ),
            },
            {"match_score": 91, "priority": "High", "good_fit": "Direct match on Python/FastAPI/AWS.", "weak_areas": "", "red_flags": ""},
            "Applied",
            "Follow up on application status.",
        ),
        (
            {
                "title": "Platform Engineer",
                "company": "Cobalt Systems",
                "location": "London, UK", "remote_type": "hybrid",
                "url": "https://jobs.example.com/cobalt/platform-engineer",
                "source": "Seed", "salary_min": 85000, "salary_max": 110000,
                "opportunity_type": "job", "classification": "job", "importable": True,
                "description": (
                    "Platform Engineer to build internal developer tooling and CI/CD pipelines. "
                    "Requirements: Docker, Kubernetes, Python, and infrastructure-as-code. "
                    "Hybrid in London, 2 days on-site. Salary 85k-110k."
                ),
            },
            {"match_score": 78, "priority": "Medium", "good_fit": "Strong tooling and CI/CD overlap.", "weak_areas": "Limited Kubernetes depth.", "red_flags": "Hybrid on-site requirement."},
            "Interview",
            None,
        ),
        (
            {
                "title": "Full Stack Developer",
                "company": "Brightwave",
                "location": "Remote", "remote_type": "remote",
                "url": "https://jobs.example.com/brightwave/full-stack-developer",
                "source": "Seed", "salary_min": 70000, "salary_max": 95000,
                "opportunity_type": "job", "classification": "job", "importable": True,
                "description": (
                    "Full Stack Developer for a SaaS analytics product. React/TypeScript frontend, "
                    "FastAPI backend. Requirements: 3+ years full stack, SQL, REST APIs. Fully remote."
                ),
            },
            {"match_score": 84, "priority": "High", "good_fit": "React + FastAPI match.", "weak_areas": "", "red_flags": ""},
            "New", None,
        ),
        (
            {
                "title": "Backend Engineering Internship",
                "company": "Quanta",
                "location": "Remote", "remote_type": "remote",
                "url": "https://jobs.example.com/quanta/backend-internship",
                "source": "Seed",
                "opportunity_type": "internship", "classification": "internship", "importable": True,
                "description": "Summer backend engineering internship working with Python and FastAPI. "
                "Open to students and early-career engineers. Mentorship provided. Remote.",
            },
            None, None, None,
        ),
        (
            {
                "title": "Freelance API Developer (6 months)",
                "company": "Meridian Pay",
                "location": "Remote", "remote_type": "remote",
                "url": "https://jobs.example.com/meridian/freelance-api-developer",
                "source": "Seed", "salary_min": 500, "salary_max": 650,
                "opportunity_type": "freelance", "classification": "freelance", "importable": True,
                "description": (
                    "6-month contract to build payment APIs in FastAPI for a fintech platform. "
                    "Requirements: Python, REST, secure API design. £500-650/day, remote."
                ),
            },
            {"match_score": 72, "priority": "Medium", "good_fit": "Fintech API contract fits skills.", "weak_areas": "Short-term contract.", "red_flags": ""},
            "New", None,
        ),
        (
            {
                "title": "AI Builders Hackathon",
                "company": "DevTools Collective",
                "location": "Online", "remote_type": "remote",
                "url": "https://events.example.com/ai-builders-hackathon",
                "source": "Seed",
                "opportunity_type": "hackathon", "classification": "hackathon", "importable": True,
                "description": "48-hour online hackathon to build AI-powered developer tools. Prizes for top three teams.",
            },
            None, None, None,
        ),
    ]

    email = DEMO_EMAIL
    user = get_user_by_email(email)
    if user:
        user_id = int(user["user_id"])
    else:
        user_id = create_user(email=email, password_hash=hash_password(DEMO_PASSWORD), full_name=DEMO_NAME)

    ensure_user_workspace(user_id)

    profile = dict(DEMO_PROFILE)
    profile["email"] = email
    upsert_profile(profile, user_id)

    inserted = 0
    skipped = 0
    for payload, evaluation, status, followup_note in DEMO_JOBS:
        try:
            job_id = insert_job(payload, user_id)
        except Exception:
            skipped += 1
            continue
        inserted += 1
        if evaluation:
            save_evaluation(job_id, evaluation, user_id)
        if status and status != "New":
            update_status(job_id, status, "", user_id)
        if followup_note:
            create_reminder(job_id, "follow_up", utc_now(), followup_note, user_id)

    logger = logging.getLogger(__name__)
    logger.info("Database was empty — seeded demo data: user=%s, %d jobs inserted, %d skipped", email, inserted, skipped)
