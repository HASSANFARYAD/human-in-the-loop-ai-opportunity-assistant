from __future__ import annotations

from typing import Any, Dict

from .openai_client import ask_json


def generate_materials(profile: Dict[str, Any], job: Dict[str, Any], evaluation: Dict[str, Any], user_id: int | None = None) -> Dict[str, Any]:
    fallback = {
        "professional_summary": f"Experienced professional targeting {job.get('title','this role')} at {job.get('company','the company')}, with relevant skills aligned to the job requirements.",
        "cover_letter": f"Dear Hiring Team,\n\nI am interested in the {job.get('title','role')} opportunity at {job.get('company','your company')}. My background aligns with the role through hands-on experience in {profile.get('skills','relevant technologies')}. I would welcome the chance to discuss how I can contribute.\n\nSincerely,",
        "resume_bullets": "- Reframe recent projects using the same keywords as the job description.\n- Quantify business impact, latency, cost, revenue, or delivery speed where possible.\n- Move the most relevant technologies into the first third of the resume.",
        "screening_answers": "Work authorization: answer truthfully based on your situation.\nSalary: use your target range and note flexibility where appropriate.\nAvailability: provide your real notice period/start date.",
        "linkedin_message": f"Hi, I saw the {job.get('title','role')} opening at {job.get('company','your company')} and think my background could be a strong fit. I’d appreciate the chance to connect and learn more.",
        "why_fit": f"I’m a fit because my experience maps to the role’s core requirements and I can contribute across product, engineering, and delivery from day one.",
    }
    system = "You create truthful, editable job application drafts. Never invent credentials. Return only JSON."
    user = f"""
Generate tailored materials for this job. Return JSON with: professional_summary, cover_letter, resume_bullets, screening_answers, linkedin_message, why_fit.
Keep content concise, professional, editable, and grounded only in the supplied profile/CV and job.

PROFILE:\n{profile}

JOB:\n{job}

EVALUATION:\n{evaluation}
"""
    data = ask_json(system, user, fallback, user_id=user_id)
    for k, v in fallback.items():
        data.setdefault(k, v)
    return data
