from __future__ import annotations

import asyncio
import logging
from typing import Any

from job_assistant.db import (
    get_profile, insert_job, save_evaluation, get_automation_preferences,
    create_auto_apply_log, update_auto_apply_log, get_daily_apply_count,
    get_collection, utc_now,
)
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.scoring import score_job
from job_assistant.services.linkedin_easy_apply import easy_apply_for_job
from job_assistant.services.email_outreach import send_outreach_email, list_templates

logger = logging.getLogger(__name__)

LINKEDIN_SOURCES = {"LinkedIn", "linkedin"}
PUBLIC_API_SOURCES = {"RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "RemoteOK", "Hacker News Who is hiring", "The Muse"}
MULTI_SOURCES = {"USAJobs", "Reed.co.uk", "Coroflot", "GulfTalent", "Naukri", "Zippia", "Xing", "NaukriGulf", "WizeHire", "MyCariera", "Linq", "CareerAddict", "iRecruitee", "InstaHyre", "Skywalker", "WhatJobs", "CareerPage"}


def execute_auto_apply_pipeline(
    user_id: int,
    workspace_id: int | None = None,
    query: str = "",
    sources: list[str] | None = None,
    platforms: list[str] | None = None,
    channels: list[str] | None = None,
    min_score: int = 60,
    max_applications: int = 5,
    dry_run: bool = True,
    loop_id: int | None = None,
    run_id: int | None = None,
) -> dict[str, Any]:
    sources = sources or ["LinkedIn", "RemoteJobs.org"]
    channels = channels or ["linkedin"]
    platforms = platforms or ["linkedin", "email"]

    profile = get_profile(user_id)
    if not profile:
        return {"status": "error", "message": "No profile configured"}

    jobs_discovered = 0
    jobs_qualified = 0
    applications_attempted = 0
    applications_submitted = 0
    applications_failed = 0
    budget_consumed = 0
    errors = []

    discovered_jobs = _discover_jobs(query, sources, user_id)
    jobs_discovered = len(discovered_jobs)

    for job in discovered_jobs:
        if applications_submitted >= max_applications:
            logger.info("Reached max_applications (%d), stopping pipeline", max_applications)
            break

        try:
            job_id = insert_job(job, user_id, workspace_id=workspace_id)
        except Exception:
            logger.warning("Failed to insert job (likely duplicate): %s", job.get("title"))
            continue

        evaluation = score_job(profile, job, user_id=user_id)
        save_evaluation(job_id, evaluation, user_id)
        match_score = int(evaluation.get("match_score", 0) or 0)

        if match_score < min_score:
            logger.info("Job %d score %d < threshold %d, skipping", job_id, match_score, min_score)
            continue

        jobs_qualified += 1
        job["_job_id"] = job_id
        job["_score"] = match_score

    qualified_jobs = [j for j in discovered_jobs if j.get("_job_id") and j.get("_score", 0) >= min_score]
    qualified_jobs.sort(key=lambda j: j.get("_score", 0), reverse=True)
    qualified_jobs = qualified_jobs[:max_applications]

    for job in qualified_jobs:
        if applications_submitted >= max_applications:
            break

        job_id = job["_job_id"]
        score = job["_score"]
        channel = _classify_channel(job, channels)

        log_id = create_auto_apply_log(
            user_id, job_id, channel,
            loop_id=loop_id, run_id=run_id,
            score=score, workspace_id=workspace_id,
        )

        if channel == "linkedin_easy_apply":
            result = _apply_via_linkedin(job, user_id, dry_run=dry_run)
        elif channel == "email":
            result = _apply_via_email(job, profile, dry_run=dry_run)
        else:
            result = {"status": "skipped", "reason": f"Unsupported channel: {channel}"}

        if result.get("status") == "submitted":
            applications_submitted += 1
            budget_consumed += 1
            update_auto_apply_log(log_id, user_id, status="submitted", details=result)
        elif result.get("status") == "dry_run":
            applications_submitted += 1
            budget_consumed += 1
            update_auto_apply_log(log_id, user_id, status="submitted", details={"dry_run": True, **result})
        elif result.get("status") == "failed":
            applications_failed += 1
            update_auto_apply_log(log_id, user_id, status="failed", error_message=result.get("reason"), details=result)
            errors.append({"job_id": job_id, "error": result.get("reason")})
        else:
            update_auto_apply_log(log_id, user_id, status="skipped", details=result)

        applications_attempted += 1

    return {
        "status": "completed" if not errors else "completed_with_errors",
        "jobs_discovered": jobs_discovered,
        "jobs_qualified": jobs_qualified,
        "applications_attempted": applications_attempted,
        "applications_submitted": applications_submitted,
        "applications_failed": applications_failed,
        "budget_consumed": budget_consumed,
        "errors": errors,
    }


def _discover_jobs(query: str, sources: list[str], user_id: int) -> list[dict[str, Any]]:
    all_jobs = []

    api_sources = [s for s in sources if s in PUBLIC_API_SOURCES]
    if api_sources:
        try:
            jobs = discover_public_opportunities(
                query=query,
                sources=api_sources,
                limit_per_source=20,
            )
            all_jobs.extend(jobs)
        except Exception as e:
            logger.error("Public discovery failed: %s", e)

    multi_sources = [s for s in sources if s in MULTI_SOURCES]
    if multi_sources:
        try:
            from job_assistant.services.multi_source_discovery import discover_multi_source
            jobs = discover_multi_source(
                query=query,
                sources=multi_sources,
                limit_per_source=10,
            )
            all_jobs.extend(jobs)
        except Exception as e:
            logger.error("Multi-source discovery failed: %s", e)

    linkedin_sources = [s for s in sources if s in LINKEDIN_SOURCES]
    if linkedin_sources:
        try:
            from job_assistant.services.parsing import extract_job_from_text
            from job_assistant.services.rapidapi_linkedin import (
                search_linkedin_jobs, rapidapi_items_to_opportunities,
            )
            from job_assistant.db import get_integration_settings
            rapidapi = get_integration_settings(user_id, "rapidapi_linkedin")
            api_key = rapidapi.get("api_key", "")
            if api_key:
                items = search_linkedin_jobs(api_key, query, "Remote", 0)
                jobs = rapidapi_items_to_opportunities(items)
                all_jobs.extend(jobs)
        except Exception as e:
            logger.error("LinkedIn API discovery failed: %s", e)

    return all_jobs


def _classify_channel(job: dict[str, Any], available_channels: list[str]) -> str:
    url = job.get("url", "")
    has_recruiter_email = bool(job.get("recruiter_email"))
    is_linkedin = "linkedin.com" in url

    if is_linkedin and "linkedin_easy_apply" in available_channels:
        return "linkedin_easy_apply"
    if has_recruiter_email and "email" in available_channels:
        return "email"
    if "linkedin_easy_apply" in available_channels:
        return "linkedin_easy_apply"
    if "email" in available_channels:
        return "email"
    return available_channels[0] if available_channels else "email"


def _apply_via_linkedin(job: dict[str, Any], user_id: int, dry_run: bool = True) -> dict[str, Any]:
    url = job.get("url", "")
    if not url or "linkedin.com" not in url:
        return {"status": "skipped", "reason": "Not a LinkedIn URL"}
    try:
        return asyncio.run(easy_apply_for_job(user_id, url, dry_run=dry_run))
    except Exception as e:
        return {"status": "failed", "reason": str(e)}


def _apply_via_email(job: dict[str, Any], profile: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
    recruiter_email = job.get("recruiter_email", "")
    if not recruiter_email:
        return {"status": "skipped", "reason": "No recruiter email available"}
    try:
        if dry_run:
            return {"status": "dry_run", "reason": "Email would be sent", "to": recruiter_email}
        templates = list_templates(profile.get("user_id", 1))
        default_template = next((t for t in templates if t.get("is_default") or t.get("name") == "Standard Application"), None)
        if not default_template:
            return {"status": "failed", "reason": "No email template found"}
        template_id = default_template["_id"]
        job_id = job.get("_job_id", 0)
        variables = {
            "job_title": job.get("title", ""),
            "company_name": job.get("company", ""),
            "full_name": profile.get("full_name", ""),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "skill_area": ", ".join(profile.get("skills", []) if isinstance(profile.get("skills"), list) else [profile.get("skills", "")]),
        }
        result = send_outreach_email(
            user_id=profile.get("user_id", 1),
            job_id=job_id,
            template_id=template_id,
            to_email=recruiter_email,
            variables=variables,
        )
        return {"status": "submitted" if result.success else "failed", "reason": result.error if not result.success else "", "to": recruiter_email, "message_id": result.message_id}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}
