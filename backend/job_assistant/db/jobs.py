from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

import pymongo
from pymongo import errors as pymongo_errors

from job_assistant.db.core import (
    _as_text, _next_id, _safe_json_loads, _strip_id, _workspace_scope_for_user,
    add_audit_log, get_collection, utc_now,
    JOB_LIKE_TYPES, OPPORTUNITY_TYPES, STATUSES,
)

__all__ = [
    "_job_with_id_alias",
    "insert_job", "_content_hash", "_normalize_for_fuzzy", "_fuzzy_match_title_company",
    "FUZZY_DUP_THRESHOLD", "COMMON_ABBREVIATIONS",
    "job_exists", "job_url_exists", "list_jobs", "get_job", "delete_job",
    "JOB_DATA_TABLE_ORDER",
    "clear_job_data",
    "save_evaluation", "get_evaluation",
    "cleanup_non_opportunity_records",
    "save_materials", "get_materials",
    "update_status",
    "save_resume_review", "list_resume_reviews",
    "save_interview_prep", "list_interview_prep",
    "save_recording", "list_recordings",
    "create_reminder", "create_followup_reminders", "due_reminders",
]


def _job_with_id_alias(doc: dict) -> dict:
    item = _strip_id(doc)
    if item and "job_id" in item:
        item["id"] = item["job_id"]
    return item


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


def create_reminder(job_id: int, kind: str, remind_at: str, note: str, user_id: int = 1) -> None:
    if not get_collection("jobs").find_one({"job_id": job_id, "user_id": user_id}):
        raise ValueError("Job not found for user")
    rid = _next_id("reminder_id")
    get_collection("reminders").insert_one({
        "reminder_id": rid, "job_id": job_id, "kind": kind,
        "remind_at": remind_at, "note": note, "created_at": utc_now(),
    })


def create_followup_reminders(after_days: int = 7) -> int:
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
