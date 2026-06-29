from __future__ import annotations

from typing import Any, Dict, Optional

from .openai_client import ask_json
from .job_context import build_job_context, choose_primary_focus_area


def generate_materials(
    profile: Dict[str, Any],
    job: Dict[str, Any],
    evaluation: Dict[str, Any],
    user_id: int | None = None,
    workspace_id: Optional[int] = None,
) -> Dict[str, Any]:
    context = build_job_context(profile, job)
    primary_focus = choose_primary_focus_area(context["focus_areas"])
    secondary_focus = next((area for area in context["focus_areas"] if area != primary_focus), primary_focus)
    highlight = context["highlights"][0] if context["highlights"] else job.get("description") or job.get("raw_text") or ""
    skill_line = ", ".join(context["skills"][:4] or context["keywords"][:4] or ["your core experience"])
    fallback = {
        "professional_summary": f"Experienced professional targeting {context['title']} at {context['company']}, with hands-on experience in {skill_line} and a clear fit for {primary_focus.lower()}.",
        "cover_letter": (
            f"Dear Hiring Team,\n\n"
            f"I am interested in the {context['title']} opportunity at {context['company']}. "
            f"The posting emphasizes {primary_focus.lower()} and {secondary_focus.lower()}, and that matches my background in {skill_line}. "
            f"I was especially drawn to the job detail: {highlight[:140]}. "
            f"I would welcome the chance to discuss how I can contribute.\n\nSincerely,"
        ),
        "resume_bullets": (
            f"- Reframe recent projects around {primary_focus.lower()} using the exact language from the posting where it truthfully matches your work.\n"
            f"- Add a second bullet that shows delivery strength in {secondary_focus.lower()} with a concrete result, metric, or handoff outcome.\n"
            f"- Move the most relevant technologies, especially {skill_line}, into the first third of the resume."
        ),
        "screening_answers": "Work authorization: answer truthfully based on your situation.\nSalary: use your target range and note flexibility where appropriate.\nAvailability: provide your real notice period/start date.\nTime-zone overlap: confirm your actual working hours if the posting asks for it.",
        "linkedin_message": f"Hi, I saw the {context['title']} opening at {context['company']} and noticed the emphasis on {primary_focus.lower()}. My background in {skill_line} seems well aligned, and I would appreciate the chance to connect.",
        "why_fit": f"I am a fit because this role specifically asks for {primary_focus.lower()} and {secondary_focus.lower()}, which maps to my background in {skill_line} and my experience shipping production work.",
        "job_focus_areas": context["focus_areas"],
        "job_highlights": context["highlights"],
        "job_keywords": context["keywords"],
    }
    import json as _json
    system = "You create truthful, editable job application drafts. Return only JSON. Use the job-specific details to make each output distinct."
    profile_safe = {k: v for k, v in (profile or {}).items() if k != "cv_text"}
    profile_safe["cv_text_snippet"] = (profile.get("cv_text") or "")[:4000]
    eval_safe = _json.dumps(evaluation, default=str)[:4000] if evaluation else ""
    user = f"""
Generate tailored materials for this specific job. Return JSON with: professional_summary, cover_letter, resume_bullets, screening_answers, linkedin_message, why_fit.
Keep content concise, professional, editable, and grounded only in the supplied profile/CV and job.
Do not reuse generic language across jobs. Make the company, role, responsibilities, and fit analysis visibly specific to this posting.

PROFILE:
{_json.dumps(profile_safe, default=str)[:8000]}

JOB SNAPSHOT:
title: {job.get("title", "")}
company: {job.get("company", "")}
location: {job.get("location", "")}
remote_type: {job.get("remote_type", "")}
description: {(job.get("description") or job.get("raw_text") or "")[:4000]}
job_keywords: {context["keywords"][:20]}
job_focus_areas: {context["focus_areas"][:10]}
job_highlights: {context["highlights"][:5]}

EVALUATION:
{eval_safe}
"""
    data = ask_json(system, user, fallback, user_id=user_id, task_type="materials_generation", workspace_id=workspace_id)
    for k, v in fallback.items():
        data.setdefault(k, v)
    data.setdefault("job_keywords", context["keywords"])
    data.setdefault("job_focus_areas", context["focus_areas"])
    data.setdefault("job_highlights", context["highlights"])
    return data
