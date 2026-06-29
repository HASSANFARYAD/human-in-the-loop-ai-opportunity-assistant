from __future__ import annotations

import logging

from job_assistant.db.core import get_collection, utc_now
from job_assistant.db.users import create_user, get_user_by_email
from job_assistant.db.profiles import upsert_profile
from job_assistant.db.jobs import insert_job, save_evaluation, update_status, create_reminder
from job_assistant.db.enterprise import ensure_user_workspace

__all__ = [
    "needs_seed", "seed_demo_data",
]


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
