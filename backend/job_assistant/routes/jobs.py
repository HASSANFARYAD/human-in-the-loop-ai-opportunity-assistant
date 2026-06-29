from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.auth import current_user
from job_assistant.db import (
    cleanup_non_opportunity_records,
    create_reminder,
    delete_job,
    due_reminders,
    get_evaluation,
    get_job,
    get_materials,
    get_profile,
    get_job as get_job_detail,
    insert_job,
    list_interview_prep,
    list_jobs,
    list_resume_reviews,
    record_score_feedback,
    save_evaluation,
    save_interview_prep,
    save_materials,
    save_resume_review,
    update_status,
)
from job_assistant.services.generation import generate_materials
from job_assistant.services.company_research import build_company_context
from job_assistant.services.job_context import build_job_context, choose_primary_focus_area, extract_profile_skills
from job_assistant.services.opportunity_classifier import (
    annotate_opportunity,
    is_job_like,
    scoring_gate,
)
from job_assistant.services.resume_builder import (
    RESUME_TEMPLATES,
    RESUME_STRUCTURE_KEYS,
    is_valid_template,
    render_resume_docx,
)
from job_assistant.services.scoring import score_job

logger = logging.getLogger(__name__)

router = APIRouter()


class JobCreate(BaseModel):
    workspace_id: Optional[int] = None
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    remote_type: Optional[str] = None
    url: Optional[str] = None
    source: str
    description: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    deadline: Optional[str] = None
    opportunity_type: str = "job"
    classification: Optional[str] = None
    classification_reason: Optional[str] = None
    classification_confidence: Optional[float] = None
    opportunity_confidence: Optional[float] = None
    importable: Optional[bool] = None
    blocked_reason: Optional[str] = None


class ScoreFeedbackIn(BaseModel):
    signal: str
    workspace_id: Optional[int] = None


class BatchScoreIn(BaseModel):
    job_ids: list[int] = Field(default_factory=list)
    score_all_unscored: bool = False
    profile_id: Optional[int] = None


class ResumeReviewIn(BaseModel):
    job_id: Optional[int] = None
    resume_text: str = ""
    target_role: str = ""


class ReminderCreate(BaseModel):
    job_id: int
    kind: str
    remind_at: str
    note: Optional[str] = None


def _profile_has_resume_context(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    return any(str(profile.get(key) or "").strip() for key in ["cv_text", "skills", "target_roles", "preferred_role"])


def _require_ai_configuration(user_id: int, task_type: str) -> None:
    route = ai_orchestrator.resolve_route(user_id, task_type=task_type)
    if not (route.settings.get("api_key") or "").strip():
        raise HTTPException(
            status_code=400,
            detail="LLM provider configuration is missing in database settings. Configure an active AI provider before generating this output.",
        )


def _generate_resume_review(profile: dict[str, Any], job: dict[str, Any] | None, resume_text: str = "", target_role: str = "") -> dict[str, Any]:
    resume = resume_text.strip() or str(profile.get("cv_text") or "")
    job = job or {}
    context = build_job_context(profile, job)
    primary_focus = choose_primary_focus_area(context["focus_areas"])
    profile_terms = {term.lower() for term in extract_profile_skills(profile, limit=20)}
    missing = sorted(
        list(
            {keyword.lower() for keyword in context["keywords"]}
            .difference(profile_terms)
            & {"python", "react", "next.js", "sql", "aws", "azure", "fastapi", "typescript", "leadership", "analytics", "openai", "claude", "zapier", "n8n"}
        )
    )
    return {
        "summary": f"Resume review for {target_role or job.get('title') or profile.get('preferred_role') or 'target role'}.",
        "strengths": [
            "Existing resume/profile text is available for tailoring." if resume else "Add resume text to unlock stronger feedback.",
            f"Profile skills can be mapped into {primary_focus.lower()} language.",
        ],
        "weaknesses": [
            "Quantify recent achievements with business or delivery impact.",
            f"Move the most relevant keywords for {context['title']} into the top third of the resume.",
        ],
        "missing_keywords": missing,
        "job_focus_areas": context["focus_areas"],
        "job_highlights": context["highlights"],
        "formatting_suggestions": [
            "Use concise bullets that start with action verbs.",
            "Keep sections scan-friendly for ATS and recruiter review.",
        ],
        "role_alignment": f"Good baseline alignment; improve by mirroring the {context['title']} title, core stack, and responsibility language.",
        "recommended_changes": [
            f"Add 2-3 bullets tied directly to {primary_focus.lower()} job responsibilities.",
            "Replace generic summaries with target-role positioning.",
        ],
        "improved_resume_response": f"Draft improvement: emphasize measurable outcomes, relevant tools, and the exact {context['title']} target role in the summary and first experience section.",
    }


def _keywords_from_job(job: dict[str, Any]) -> list[str]:
    text = " ".join(str(job.get(key) or "") for key in ["title", "description", "raw_text"])
    important = [
        term for term in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", text)
        if term.lower() not in {"and", "the", "with", "for", "from", "that", "this", "you", "our", "are", "will", "role", "job"}
    ]
    seen: set[str] = set()
    keywords: list[str] = []
    for term in important:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(term)
    return keywords[:18]


def _generate_tailored_resume(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    context = build_job_context(profile, job)
    role = context["title"]
    company = context["company"]
    skills = context["skills"]
    keywords = context["keywords"]
    focus_areas = context["focus_areas"]
    highlights = context["highlights"]
    emphasized_skills = [skill for skill in skills if skill.lower() in " ".join(keywords).lower()] or skills[:8] or keywords[:8]
    primary_focus = choose_primary_focus_area(focus_areas)
    secondary_focus = next((area for area in focus_areas if area != primary_focus), primary_focus)
    highlight = highlights[0] if highlights else ""
    summary = (
        f"{profile.get('years_experience') or 'Experienced'} professional targeting {role} at {company}, "
        f"with hands-on experience in {', '.join(emphasized_skills[:5]) or 'the role requirements'} and a clear fit for {primary_focus.lower()}."
    )
    bullets = [
        f"Delivered work aligned with {primary_focus.lower()} using {', '.join(emphasized_skills[:4]) or 'relevant tools and practices'}.",
        f"Translated {secondary_focus.lower()} requirements into maintainable, measurable solutions that can be referenced in the {role} resume.",
        f"Collaborated across stakeholders to ship reliable improvements; job-specific cue: {highlight[:120] or 'highlight the most relevant project outcome from your history'}.",
    ]
    draft = "\n".join([
        "Professional Summary", summary, "",
        "Selected Experience Bullets",
        *[f"- {bullet}" for bullet in bullets], "",
        "Skills", ", ".join(emphasized_skills[:12] or keywords[:12]),
    ])
    return {
        "type": "tailored_resume", "target_role": role, "company": company,
        "tailored_summary": summary, "tailored_experience_bullets": bullets,
        "skills_to_emphasize": emphasized_skills[:12], "keywords_to_include": keywords,
        "job_focus_areas": focus_areas, "job_highlights": highlights,
        "optional_cover_note": f"I am interested in the {role} role at {company} because the posting emphasizes {primary_focus.lower()} and {secondary_focus.lower()}, which maps directly to my background.",
        "application_guidance": [
            "Keep claims grounded in your real resume and project history.",
            "Add metrics to the bullets before submitting.",
            "Mirror the most relevant job keywords where they truthfully match your experience.",
        ],
        "resume_draft": draft, "generation_source": "local_fallback",
    }


def _generate_interview_prep(profile: dict[str, Any], job: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    context = build_job_context(profile, job)
    role = context["title"]
    company = context["company"]
    focus_areas = context["focus_areas"]
    highlights = context["highlights"]
    skills = context["skills"]
    primary_focus = choose_primary_focus_area(focus_areas)
    other_focuses = [area for area in focus_areas if area != primary_focus]
    secondary_focus = other_focuses[0] if other_focuses else primary_focus
    third_focus = other_focuses[1] if len(other_focuses) > 1 else primary_focus
    skill_line = ", ".join(skills[:4] or context["keywords"][:4] or ["your stack"])
    highlight_line = highlights[0] if highlights else f"the requirements for {role}"
    company_context = build_company_context(company)
    company_brief = company_context or ""
    return {
        "summary": f"Interview preparation for {role} at {company}.",
        "company_research_brief": company_brief,
        "behavioral_questions": [
            f"Tell me about a time you delivered {primary_focus.lower()} under a tight timeline.",
            f"Describe a situation where you had to balance {secondary_focus.lower()} with quality or stakeholder expectations.",
            f"Give an example of improving a process or system similar to the work described in this posting.",
            f"How does your experience align with {company}'s culture or industry?" if company_brief else "",
        ],
        "technical_questions": [
            f"Walk through how your skills in {skill_line} apply to {primary_focus.lower()} for this role.",
            f"How would you approach a production issue that touches {secondary_focus.lower()} and needs careful validation?",
            f"What tradeoffs would you consider when designing a solution for {third_focus.lower()} in a fast-moving environment?",
        ],
        "role_specific_questions": [
            f"What attracts you to the {role} responsibilities at {company}?",
            f"Which requirement in the job description best matches your recent experience with {primary_focus.lower()}?",
        ],
        "company_job_specific_questions": [
            f"The posting highlights: {highlight_line[:140]}. How would you show direct experience with that?",
            f"What part of the {role} role at {company} feels most aligned with your background?",
        ],
        "suggested_answer_outlines": [
            f"Use STAR, then close by tying the answer back to {primary_focus.lower()} and the impact you delivered.",
            f"Reference a concrete project that shows {secondary_focus.lower()} and keep the answer under two minutes.",
        ],
        "star_format_guidance": [
            "Situation: give only the minimum context needed.",
            "Task: state the goal or constraint clearly.",
            "Action: focus on what you personally did.",
            "Result: include a measurable or observable outcome.",
        ],
        "weakness_improvement_prompts": [
            f"Prepare one example that proves you can handle {primary_focus.lower()} without inventing details.",
            f"Prepare one example that proves you can communicate tradeoffs around {secondary_focus.lower()}.",
        ],
        "candidate_questions": [
            f"What does success look like for {role} in the first 30, 60, and 90 days?",
            f"Where does {company} need the most help relative to {highlight_line[:90]}?",
        ],
        "final_preparation_checklist": [
            f"Have one example ready for {primary_focus.lower()}",
            f"Have one example ready for {secondary_focus.lower()}",
            "Prepare one metric-driven story and one learning story.",
            "Review the company, the job description, and your resume side by side before the interview.",
        ],
        "talking_points": [
            evaluation.get("good_fit") or f"Highlight direct overlap between your experience and the {role} responsibilities.",
            f"Prepare one metric-driven achievement and one story tied to {primary_focus.lower()}.",
        ],
        "questions_to_ask": [
            "What would success look like in the first 90 days?",
            f"Which team priorities are driving this opening at {company}?",
        ],
        "company_research_brief": company_brief,
        "generation_source": "local_fallback",
    }


def _llm_resume_review(profile: dict[str, Any], job: dict[str, Any] | None, resume_text: str, target_role: str, user_id: int) -> dict[str, Any]:
    _require_ai_configuration(user_id, "resume_review")
    fallback = _generate_resume_review(profile, job, resume_text, target_role)
    system = (
        "You are an expert resume reviewer. Return JSON only with keys: overall_assessment, strengths, weaknesses, "
        "missing_keywords, role_alignment_feedback, formatting_suggestions, ats_improvement_suggestions, "
        "recommended_bullet_rewrites, summary_rewrite_suggestion, priority_action_list, final_improved_resume_guidance."
    )
    context = {
        "user_profile": {k: v for k, v in (profile or {}).items() if k != "cv_text"},
        "target_role": target_role or (job or {}).get("title") or profile.get("preferred_role") or profile.get("target_roles"),
        "selected_opportunity": job or {},
        "resume_text": (resume_text or profile.get("cv_text") or "")[:4000],
        "user_preferences": {
            "country": profile.get("country"), "role": profile.get("preferred_role") or profile.get("target_roles"),
            "job_type": profile.get("job_preferences"), "remote_preference": profile.get("remote_preference"),
            "platforms": profile.get("platforms"),
        },
    }
    context_json = json.dumps(context, default=str)
    if len(context_json) > 15000:
        context_json = context_json[:15000]
    review = ai_orchestrator.ask_json(system, context_json, fallback, user_id=user_id, task_type="resume_review", workspace_id=job.get("workspace_id") if job else None)
    if review.get("_ai_error"):
        raise HTTPException(status_code=502, detail=f"LLM resume review failed: {review.get('_ai_error')}")
    review.setdefault("generation_source", "llm")
    return review


def _llm_interview_prep(profile: dict[str, Any], job: dict[str, Any], evaluation: dict[str, Any], user_id: int) -> dict[str, Any]:
    _require_ai_configuration(user_id, "interview_prep")
    fallback = _generate_interview_prep(profile, job, evaluation)
    latest_reviews = list_resume_reviews(user_id, job_id=int(job["id"]), limit=1)
    job_context = build_job_context(profile, job)
    company_name = str(job.get("company") or "").strip()
    company_context = build_company_context(company_name, user_id=user_id) if company_name else ""
    system = (
        "You are an expert interview coach. Return JSON only with keys: behavioral_questions, technical_questions, "
        "role_specific_questions, company_job_specific_questions, suggested_answer_outlines, star_format_guidance, "
        "weakness_improvement_prompts, candidate_questions, final_preparation_checklist, company_research_brief."
    )
    context = {
        "user_profile": {k: v for k, v in (profile or {}).items() if k != "cv_text"},
        "resume_text": (profile.get("cv_text") or "")[:4000],
        "selected_opportunity": {k: v for k, v in (job or {}).items() if k not in ("raw_text", "description")},
        "job_description": (job.get("description") or "")[:4000],
        "required_skills": ((job.get("raw_text") or job.get("description") or "")[:3000]),
        "company_name": company_name,
        "company_research": company_context,
        "role_title": job.get("title"),
        "job_keywords": job_context["keywords"][:20],
        "job_focus_areas": job_context["focus_areas"][:10],
        "job_highlights": job_context["highlights"][:5],
        "ai_score": evaluation,
        "resume_review_findings": latest_reviews[0] if latest_reviews else {},
    }
    context_json = json.dumps(context, default=str)
    if len(context_json) > 15000:
        context_json = context_json[:15000]
    prep = ai_orchestrator.ask_json(system, context_json, fallback, user_id=user_id, task_type="interview_prep", workspace_id=job.get("workspace_id"))
    if prep.get("_ai_error"):
        raise HTTPException(status_code=502, detail=f"LLM interview preparation failed: {prep.get('_ai_error')}")
    prep.setdefault("generation_source", "llm")
    return prep


def _fallback_resume_structure(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    skills = [s.strip() for s in str(profile.get("skills") or "").split(",") if s.strip()]
    return {
        "full_name": profile.get("full_name") or "Your Name",
        "headline": job.get("title") or profile.get("preferred_role") or profile.get("target_roles") or "",
        "contact": {"email": profile.get("email") or "", "location": profile.get("locations") or profile.get("country") or "", "phone": "", "linkedin": "", "website": ""},
        "summary": (str(profile.get("cv_text") or "").strip()[:600]) or "Experienced professional aligned to the target role.",
        "skills": skills, "experience": [], "education": [], "certifications": [], "projects": [],
    }


def _llm_structured_resume(profile: dict[str, Any], job: dict[str, Any], user_id: int) -> dict[str, Any]:
    fallback = _fallback_resume_structure(profile, job)
    job_context = build_job_context(profile, job)
    system = (
        "You are an expert resume writer. Return JSON only describing a truthful, ATS-friendly resume tailored to the "
        "target job, grounded strictly in the supplied resume text and profile. Do NOT invent employers, job titles, "
        "dates, degrees, certifications, or metrics that are not present in the source. Leave fields empty if unknown."
    )
    context = {
        "resume_text": (profile.get("cv_text") or "")[:4000],
        "profile": {k: v for k, v in (profile or {}).items() if k != "cv_text"},
        "job": {
            "title": job.get("title"), "company": job.get("company"),
            "description": (job.get("description") or job.get("raw_text") or "")[:4000],
            "keywords": job_context["keywords"][:20], "focus_areas": job_context["focus_areas"][:10],
        },
        "output_schema": {
            "full_name": "string", "headline": "string (target job title)",
            "contact": {"email": "string", "phone": "string", "location": "string", "linkedin": "string", "website": "string"},
            "summary": "string (3-4 sentence professional summary tailored to the job)",
            "skills": ["string"],
            "experience": [{"title": "string", "company": "string", "location": "string", "start": "string", "end": "string", "bullets": ["string"]}],
            "education": [{"degree": "string", "institution": "string", "location": "string", "year": "string"}],
            "certifications": ["string"], "projects": [{"name": "string", "description": "string"}],
        },
        "required_output_keys": RESUME_STRUCTURE_KEYS,
    }
    context_json = json.dumps(context, default=str)
    if len(context_json) > 15000:
        context_json = context_json[:15000]
    structure = ai_orchestrator.ask_json(system, context_json, fallback, user_id=user_id, task_type="resume_document", workspace_id=job.get("workspace_id"))
    if structure.get("_ai_error"):
        structure = fallback
    for key in RESUME_STRUCTURE_KEYS:
        structure.setdefault(key, fallback.get(key))
    return structure


def _llm_tailored_resume(profile: dict[str, Any], job: dict[str, Any], user_id: int) -> dict[str, Any]:
    fallback = _generate_tailored_resume(profile, job)
    route = ai_orchestrator.resolve_route(user_id, task_type="resume_tailoring")
    job_context = build_job_context(profile, job)
    system = (
        "You are an expert resume writer. Return JSON only. Create a truthful tailored resume draft grounded only in "
        "the supplied resume/profile and job description. Do not invent employers, degrees, certifications, metrics, or credentials."
    )
    context = {
        "resume_text": (profile.get("cv_text") or "")[:4000],
        "profile": {k: v for k, v in (profile or {}).items() if k != "cv_text"},
        "job": {
            "title": job.get("title"), "company": job.get("company"),
            "description": (job.get("description") or job.get("raw_text") or "")[:4000],
            "location": job.get("location"), "remote_type": job.get("remote_type"),
            "keywords": job_context["keywords"][:20], "focus_areas": job_context["focus_areas"][:10],
            "highlights": job_context["highlights"][:5],
        },
        "required_output_keys": [
            "tailored_summary", "tailored_experience_bullets", "skills_to_emphasize",
            "keywords_to_include", "optional_cover_note", "application_guidance", "resume_draft",
        ],
    }
    context_json = json.dumps(context, default=str)
    if len(context_json) > 15000:
        context_json = context_json[:15000]
    tailored = ai_orchestrator.ask_json(system, context_json, fallback, user_id=user_id, task_type="resume_tailoring", workspace_id=job.get("workspace_id"))
    for key, value in fallback.items():
        tailored.setdefault(key, value)
    tailored["resume_draft"] = _resume_draft_to_text(tailored.get("resume_draft"))
    tailored["type"] = "tailored_resume"
    tailored["target_role"] = tailored.get("target_role") or job.get("title") or "target role"
    tailored["company"] = tailored.get("company") or job.get("company") or ""
    tailored["using_fallback"] = route.source == "fallback" or bool(tailored.get("_ai_error"))
    tailored["generation_source"] = "local_fallback" if tailored["using_fallback"] else "llm"
    if tailored.get("_ai_error"):
        tailored["ai_error"] = "AI generation failed; local fallback was used."
        tailored.pop("_ai_error", None)
    return tailored


def _resume_draft_to_text(draft: Any) -> str:
    if draft is None:
        return ""
    if isinstance(draft, str):
        return draft
    if isinstance(draft, (list, tuple)):
        return "\n".join(_resume_draft_to_text(item) for item in draft if item is not None)
    if isinstance(draft, dict):
        lines: list[str] = []
        for key, value in draft.items():
            label = str(key).replace("_", " ").title()
            text = _resume_draft_to_text(value)
            if not text.strip():
                continue
            if "\n" in text:
                lines.append(f"{label}:\n{text}")
            else:
                lines.append(f"{label}: {text}")
        return "\n\n".join(lines)
    return str(draft)


@router.get("/jobs")
async def list_all_jobs(workspace_id: Optional[int] = None, content_type: str = "job", type: Optional[str] = None, user: dict = Depends(current_user)):
    try:
        requested_type = type or content_type or "job"
        jobs = list_jobs(user["id"], workspace_id=workspace_id, content_type=requested_type)
        return jobs
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list jobs")


@router.post("/jobs")
async def create_job(job_data: JobCreate, user: dict = Depends(current_user)):
    try:
        payload = annotate_opportunity(job_data.dict())
        if not payload.get("importable"):
            raise HTTPException(status_code=400, detail=payload.get("blocked_reason") or "This item is not a valid opportunity and cannot be imported.")
        job_id = insert_job(payload, user["id"], workspace_id=job_data.workspace_id)
        return {"id": job_id, "status": "success", "message": "Job created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job")


@router.get("/jobs/{job_id}")
async def get_job_detail_endpoint(job_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        job = get_job(job_id, user["id"], workspace_id=workspace_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to get job")


@router.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: int, workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        job = get_job(job_id, user["id"], workspace_id=workspace_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        delete_job(job_id, user["id"], workspace_id=workspace_id)
        return {"status": "success", "message": "Job deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete job")


@router.post("/jobs/{job_id}/score")
async def score_single_job(job_id: int, profile_id: Optional[int] = None, user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"], profile_id=profile_id)
        if not profile:
            raise HTTPException(status_code=400, detail="Profile not configured")
        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        gate = scoring_gate(job)
        if not gate.importable:
            raise HTTPException(status_code=400, detail="This item is not a valid opportunity and cannot be scored.")
        evaluation = score_job(profile, job, user_id=user["id"])
        save_evaluation(job_id, evaluation, user["id"])
        return evaluation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scoring job: {e}")
        raise HTTPException(status_code=500, detail="Failed to score job")


@router.post("/jobs/score-batch")
async def score_jobs_batch(payload: BatchScoreIn, user: dict = Depends(current_user)):
    profile = get_profile(user["id"], profile_id=payload.profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Add your resume profile before scoring jobs.")
    candidate_jobs = list_jobs(user["id"], content_type="job")
    ids = [int(job_id) for job_id in payload.job_ids]
    if payload.score_all_unscored:
        ids = [int(job["job_id"]) for job in candidate_jobs if job.get("match_score") is None]
    if not ids:
        detail = "No unscored jobs are available for scoring." if payload.score_all_unscored else "Select at least one job to score."
        raise HTTPException(status_code=400, detail=detail)
    route = ai_orchestrator.resolve_route(user["id"], task_type="opportunity_scoring")
    using_fallback_scoring = route.source == "fallback"
    logger.info("Starting bulk job scoring user_id=%s requested=%s score_all_unscored=%s fallback_scoring=%s", user["id"], len(ids), payload.score_all_unscored, using_fallback_scoring)
    results = []
    for job_id in ids:
        try:
            job = get_job(int(job_id), user["id"])
            if not job:
                results.append({"job_id": job_id, "status": "failed", "error": "Job not found"})
                logger.warning("Bulk scoring failed: job not found user_id=%s job_id=%s", user["id"], job_id)
                continue
            title = str(job.get("title") or f"Job {job_id}")
            if not is_job_like(job):
                reason = "Only jobs, internships, contracts, and freelance roles can be bulk scored."
                results.append({"job_id": job_id, "title": title, "status": "skipped", "classification": job.get("classification") or job.get("opportunity_type") or "unknown", "reason": reason})
                logger.info("Bulk scoring skipped non-job user_id=%s job_id=%s reason=%s", user["id"], job_id, reason)
                continue
            if not str(job.get("description") or job.get("raw_text") or "").strip():
                reason = "Job description is missing."
                results.append({"job_id": job_id, "title": title, "status": "skipped", "reason": reason})
                logger.info("Bulk scoring skipped missing description user_id=%s job_id=%s", user["id"], job_id)
                continue
            gate = scoring_gate(job)
            if not gate.importable:
                reason = gate.blocked_reason or gate.reason or "This saved item is not ready to score."
                results.append({"job_id": job_id, "title": title, "status": "skipped", "classification": gate.classification, "reason": reason})
                logger.info("Bulk scoring skipped gated job user_id=%s job_id=%s reason=%s", user["id"], job_id, reason)
                continue
            evaluation = score_job(profile, job, user_id=user["id"])
            save_evaluation(int(job_id), evaluation, user["id"])
            results.append({"job_id": job_id, "title": title, "status": "success", "evaluation": evaluation})
        except Exception as exc:
            logger.error("Batch scoring failed for job %s: %s", job_id, exc)
            results.append({"job_id": job_id, "status": "failed", "error": str(exc)})
    succeeded = len([item for item in results if item["status"] == "success"])
    skipped = len([item for item in results if item["status"] == "skipped"])
    failed = len([item for item in results if item["status"] == "failed"])
    logger.info("Bulk job scoring completed user_id=%s requested=%s scored=%s skipped=%s failed=%s", user["id"], len(ids), succeeded, skipped, failed)
    return {
        "status": "success" if failed == 0 and skipped == 0 else "partial_success",
        "total": len(results), "total_requested": len(ids),
        "succeeded": succeeded, "scored": succeeded,
        "skipped": skipped, "failed": failed,
        "using_fallback_scoring": using_fallback_scoring, "results": results,
    }


@router.post("/jobs/{job_id}/score-feedback")
async def post_score_feedback(job_id: int, payload: ScoreFeedbackIn, user: dict = Depends(current_user)):
    job = get_job(job_id, user["id"], workspace_id=payload.workspace_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        record_score_feedback(user["id"], job_id, payload.signal, workspace_id=payload.workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "signal": payload.signal.strip().lower()}


@router.post("/jobs/cleanup-non-opportunities")
async def cleanup_non_opportunities(workspace_id: Optional[int] = None, user: dict = Depends(current_user)):
    return {"status": "success", **cleanup_non_opportunity_records(user["id"], workspace_id=workspace_id)}


@router.post("/jobs/{job_id}/generate-materials")
async def generate_job_materials(job_id: int, user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"])
        if not profile:
            raise HTTPException(status_code=400, detail="Profile not configured")
        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        evaluation = get_evaluation(job_id, user["id"])
        if not evaluation:
            evaluation = score_job(profile, job, user_id=user["id"])
            save_evaluation(job_id, evaluation, user["id"])
        materials = generate_materials(profile, job, evaluation, user_id=user["id"], workspace_id=job.get("workspace_id"))
        save_materials(job_id, materials, user["id"])
        return materials
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating materials: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate materials")


@router.get("/jobs/{job_id}/materials")
async def get_job_materials(job_id: int, user: dict = Depends(current_user)):
    try:
        materials = get_materials(job_id, user["id"])
        return materials or {}
    except Exception as e:
        logger.error(f"Error getting materials: {e}")
        raise HTTPException(status_code=500, detail="Failed to get materials")


@router.patch("/jobs/{job_id}/status")
async def update_job_status(job_id: int, status: str, notes: str = "", user: dict = Depends(current_user)):
    try:
        update_status(job_id, status, notes, user["id"])
        return {"status": "success", "message": "Job status updated"}
    except Exception as e:
        logger.error(f"Error updating status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update status")


@router.get("/resume-templates")
async def get_resume_templates(user: dict = Depends(current_user)):
    return RESUME_TEMPLATES


@router.post("/jobs/{job_id}/resume-document")
async def build_resume_document(job_id: int, template: str = "international", profile_id: Optional[int] = None, user: dict = Depends(current_user)):
    if not is_valid_template(template):
        raise HTTPException(status_code=400, detail="Unknown resume template.")
    profile = get_profile(user["id"], profile_id=profile_id)
    if not _profile_has_resume_context(profile):
        raise HTTPException(status_code=400, detail="Add resume or profile details before building a resume.")
    job = get_job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not str(job.get("description") or job.get("raw_text") or "").strip():
        raise HTTPException(status_code=400, detail="This job does not have enough description detail to build a resume.")
    structure = _llm_structured_resume(profile or {}, job, user["id"])
    try:
        docx_bytes = render_resume_docx(structure, template)
    except Exception as exc:
        logger.error(f"Resume document rendering failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to build the resume document.")
    safe_company = re.sub(r"[^A-Za-z0-9]+", "-", str(job.get("company") or job.get("title") or "resume")).strip("-").lower() or "resume"
    filename = f"resume-{safe_company}-{template}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/jobs/{job_id}/interview-prep")
async def post_job_interview_prep(job_id: int, user: dict = Depends(current_user)):
    profile = get_profile(user["id"])
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not configured")
    job = get_job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    evaluation = get_evaluation(job_id, user["id"])
    if not evaluation:
        try:
            evaluation = score_job(profile, job, user_id=user["id"])
        except Exception:
            evaluation = {"match_score": 0, "priority": "Low", "good_fit": "Highlight direct overlap between your experience and the job.", "weak_areas": "Review the job description and practice concrete examples.", "red_flags": "No automated score was available."}
    fallback = _generate_interview_prep(profile, job, evaluation)
    generation_source = "local_fallback"
    try:
        prep = _llm_interview_prep(profile, job, evaluation, user["id"])
        generation_source = "llm"
    except HTTPException:
        prep = fallback
    except Exception:
        prep = fallback
    prep.setdefault("generation_source", generation_source)
    return save_interview_prep(user["id"], job_id, prep)


@router.get("/jobs/{job_id}/interview-prep")
async def get_job_interview_prep(job_id: int, user: dict = Depends(current_user)):
    return list_interview_prep(user["id"], job_id=job_id)


@router.post("/profile/resume-review")
async def post_profile_resume_review(payload: ResumeReviewIn, user: dict = Depends(current_user)):
    profile = get_profile(user["id"])
    if not profile and not payload.resume_text.strip():
        raise HTTPException(status_code=400, detail="Profile or resume text is required")
    job = get_job(payload.job_id, user["id"]) if payload.job_id else None
    review = _llm_resume_review(profile or {}, job, payload.resume_text, payload.target_role, user["id"])
    return save_resume_review(user["id"], review, payload.job_id)


@router.get("/profile/resume-reviews")
async def get_profile_resume_reviews(job_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_resume_reviews(user["id"], job_id=job_id)


@router.post("/jobs/{job_id}/resume-review")
async def post_job_resume_review(job_id: int, payload: ResumeReviewIn, user: dict = Depends(current_user)):
    payload.job_id = job_id
    return await post_profile_resume_review(payload, user)


@router.post("/jobs/{job_id}/tailor-resume")
async def post_job_tailored_resume(job_id: int, profile_id: Optional[int] = None, user: dict = Depends(current_user)):
    profile = get_profile(user["id"], profile_id=profile_id)
    if not _profile_has_resume_context(profile):
        raise HTTPException(status_code=400, detail="Add resume or profile details before tailoring a resume.")
    job = get_job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not str(job.get("description") or job.get("raw_text") or "").strip():
        raise HTTPException(status_code=400, detail="This job does not have enough description detail to tailor a resume.")
    tailored = _llm_tailored_resume(profile or {}, job, user["id"])
    return save_resume_review(user["id"], tailored, job_id)


@router.get("/reminders")
async def list_reminders(user: dict = Depends(current_user)):
    try:
        reminders = due_reminders(user["id"])
        return reminders
    except Exception as e:
        logger.error(f"Error listing reminders: {e}")
        raise HTTPException(status_code=500, detail="Failed to list reminders")


@router.post("/reminders")
async def create_reminder_endpoint(reminder_data: ReminderCreate, user: dict = Depends(current_user)):
    try:
        create_reminder(reminder_data.job_id, reminder_data.kind, reminder_data.remind_at, reminder_data.note or "", user["id"])
        return {"status": "success", "message": "Reminder created"}
    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create reminder")
