from __future__ import annotations

import importlib


def _sample_profile() -> dict[str, str]:
    return {
        "years_experience": "8 years",
        "skills": "Python, JavaScript, React, SQL, PostgreSQL, Docker, Git, Azure, OpenAI",
        "cv_text": "Built production applications with Python, React, APIs, data pipelines, Azure, and LLM tooling.",
    }


def _sample_jobs() -> tuple[dict[str, str], dict[str, str]]:
    job_275 = {
        "title": "AI Automation & Workflow Engineer",
        "company": "Seamless Assist",
        "location": "Remote",
        "remote_type": "Remote",
        "description": (
            "Build end-to-end automation workflows using Zapier, Make, or n8n. "
            "Connect platforms via REST APIs and webhooks. Write scripts in Python or JavaScript. "
            "Build AI agents using OpenAI API, Claude API, or similar LLM APIs. "
            "Write clear SOPs and technical guides for non-technical people."
        ),
        "raw_text": "",
    }
    job_280 = {
        "title": "Python & React Engineer with AI (Remote, Latam)",
        "company": "Kubikware",
        "location": "USA",
        "remote_type": "Remote",
        "description": (
            "Strong proficiency in Python. Solid experience with React. "
            "Hands-on experience building APIs and data pipelines. "
            "Experience working with LLMs or AI-driven workflows. "
            "Experience with Azure, document processing, structured data extraction, and fast-paced production-ready code."
        ),
        "raw_text": "",
    }
    return job_275, job_280


def test_job_context_extracts_distinct_focus_areas():
    from job_assistant.services.job_context import build_job_context

    profile = _sample_profile()
    job_275, job_280 = _sample_jobs()

    context_275 = build_job_context(profile, job_275)
    context_280 = build_job_context(profile, job_280)

    assert context_275["focus_areas"] != context_280["focus_areas"]
    assert "Automation / integrations" in context_275["focus_areas"]
    assert "React / frontend delivery" in context_280["focus_areas"]
    assert context_275["keywords"] != context_280["keywords"]


def test_tailored_resume_and_interview_prep_are_job_specific():
    api = importlib.import_module("job_assistant.api")

    profile = _sample_profile()
    job_275, job_280 = _sample_jobs()

    resume_275 = api._generate_tailored_resume(profile, job_275)
    resume_280 = api._generate_tailored_resume(profile, job_280)

    assert resume_275["target_role"] != resume_280["target_role"]
    assert resume_275["job_focus_areas"] != resume_280["job_focus_areas"]
    assert "Seamless Assist" in resume_275["tailored_summary"]
    assert "Kubikware" in resume_280["tailored_summary"]
    assert any("automation" in bullet.lower() for bullet in resume_275["tailored_experience_bullets"])
    assert any("react" in bullet.lower() or "python" in bullet.lower() for bullet in resume_280["tailored_experience_bullets"])

    evaluation_275 = {"good_fit": "Automation overlap"}
    evaluation_280 = {"good_fit": "Frontend overlap"}
    prep_275 = api._generate_interview_prep(profile, job_275, evaluation_275)
    prep_280 = api._generate_interview_prep(profile, job_280, evaluation_280)

    assert prep_275["company_job_specific_questions"] != prep_280["company_job_specific_questions"]
    assert any("Seamless Assist" in question for question in prep_275["candidate_questions"])
    assert any("Kubikware" in question for question in prep_280["candidate_questions"])
    assert any("automation" in question.lower() for question in prep_275["technical_questions"])
    assert any("react" in question.lower() or "python" in question.lower() for question in prep_280["technical_questions"])


def test_materials_generation_adds_job_signals(monkeypatch):
    from job_assistant.services import generation

    profile = _sample_profile()
    job_275, job_280 = _sample_jobs()
    evaluation = {"match_score": 90, "good_fit": "Strong overlap"}

    def fake_ask_json(system, user, fallback, **kwargs):
        return dict(fallback)

    monkeypatch.setattr(generation, "ask_json", fake_ask_json)

    materials_275 = generation.generate_materials(profile, job_275, evaluation, user_id=1)
    materials_280 = generation.generate_materials(profile, job_280, evaluation, user_id=1)

    assert materials_275["professional_summary"] != materials_280["professional_summary"]
    assert materials_275["job_focus_areas"] != materials_280["job_focus_areas"]
    assert "Seamless Assist" in materials_275["cover_letter"]
    assert "Kubikware" in materials_280["cover_letter"]
    assert any("automation" in line.lower() for line in materials_275["resume_bullets"].splitlines())
    assert any("react" in line.lower() or "python" in line.lower() for line in materials_280["resume_bullets"].splitlines())
