from __future__ import annotations

"""Seed the database with a demo user, profile, and a spread of sample
opportunities (scored, with materials, applications, and reminders).

Idempotent: re-running reuses the existing demo user and skips jobs whose
URL already exists for that user. Safe to point at any environment via --db.

Examples:
    python scripts/seed_data.py
    python scripts/seed_data.py --db data/jobs.sqlite3 --email demo@example.com
"""

import argparse
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


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


# (job payload, evaluation or None, application status or None, follow-up note or None)
DEMO_JOBS = [
    (
        {
            "title": "Senior Backend Engineer",
            "company": "Northwind Labs",
            "location": "Remote (UK)",
            "remote_type": "remote",
            "url": "https://jobs.example.com/northwind/senior-backend-engineer",
            "source": "Seed",
            "salary_min": 95000,
            "salary_max": 120000,
            "opportunity_type": "job",
            "classification": "job",
            "importable": True,
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
            "location": "London, UK",
            "remote_type": "hybrid",
            "url": "https://jobs.example.com/cobalt/platform-engineer",
            "source": "Seed",
            "salary_min": 85000,
            "salary_max": 110000,
            "opportunity_type": "job",
            "classification": "job",
            "importable": True,
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
            "location": "Remote",
            "remote_type": "remote",
            "url": "https://jobs.example.com/brightwave/full-stack-developer",
            "source": "Seed",
            "salary_min": 70000,
            "salary_max": 95000,
            "opportunity_type": "job",
            "classification": "job",
            "importable": True,
            "description": (
                "Full Stack Developer for a SaaS analytics product. React/TypeScript frontend, "
                "FastAPI backend. Requirements: 3+ years full stack, SQL, REST APIs. Fully remote."
            ),
        },
        {"match_score": 84, "priority": "High", "good_fit": "React + FastAPI match.", "weak_areas": "", "red_flags": ""},
        "New",
        None,
    ),
    (
        {
            "title": "Backend Engineering Internship",
            "company": "Quanta",
            "location": "Remote",
            "remote_type": "remote",
            "url": "https://jobs.example.com/quanta/backend-internship",
            "source": "Seed",
            "opportunity_type": "internship",
            "classification": "internship",
            "importable": True,
            "description": (
                "Summer backend engineering internship working with Python and FastAPI. "
                "Open to students and early-career engineers. Mentorship provided. Remote."
            ),
        },
        None,
        None,
        None,
    ),
    (
        {
            "title": "Contract API Developer (6 months)",
            "company": "Meridian Pay",
            "location": "Remote",
            "remote_type": "remote",
            "url": "https://jobs.example.com/meridian/contract-api-developer",
            "source": "Seed",
            "salary_min": 500,
            "salary_max": 650,
            "opportunity_type": "contract",
            "classification": "contract",
            "importable": True,
            "description": (
                "6-month contract to build payment APIs in FastAPI for a fintech platform. "
                "Requirements: Python, REST, secure API design. £500-650/day, remote."
            ),
        },
        {"match_score": 72, "priority": "Medium", "good_fit": "Fintech API contract fits skills.", "weak_areas": "Short-term contract.", "red_flags": ""},
        "New",
        None,
    ),
    (
        {
            "title": "AI Builders Hackathon",
            "company": "DevTools Collective",
            "location": "Online",
            "remote_type": "remote",
            "url": "https://events.example.com/ai-builders-hackathon",
            "source": "Seed",
            "opportunity_type": "hackathon",
            "classification": "hackathon",
            "importable": True,
            "description": (
                "48-hour online hackathon to build AI-powered developer tools. Prizes for "
                "top three teams. Open to all engineers."
            ),
        },
        None,
        None,
        None,
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the database with demo data for local development and validation.")
    parser.add_argument("--db", help="SQLite database path. Defaults to APP_DB_PATH/settings.")
    parser.add_argument("--email", default=DEMO_EMAIL, help=f"Demo user email (default: {DEMO_EMAIL}).")
    parser.add_argument("--password", default=DEMO_PASSWORD, help="Demo user password (used only when creating the user).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.db:
        os.environ["APP_DB_PATH"] = args.db

    from job_assistant.auth import hash_password
    from job_assistant.db import (
        create_reminder,
        create_user,
        db_path,
        ensure_user_workspace,
        get_user_by_email,
        init_db,
        insert_job,
        save_evaluation,
        update_status,
        upsert_profile,
        utc_now,
    )

    init_db()

    email = args.email.strip().lower()
    user = get_user_by_email(email)
    if user:
        user_id = int(user["id"])
        print(f"Using existing user {email} (id={user_id}).")
    else:
        user_id = create_user(email=email, password_hash=hash_password(args.password), full_name=DEMO_NAME)
        print(f"Created user {email} (id={user_id}) with password '{args.password}'.")

    ensure_user_workspace(user_id)

    profile = dict(DEMO_PROFILE)
    profile["email"] = email
    upsert_profile(profile, user_id)
    print("Seeded profile.")

    inserted = 0
    skipped = 0
    for payload, evaluation, status, followup_note in DEMO_JOBS:
        try:
            job_id = insert_job(payload, user_id)
        except Exception as exc:  # duplicate URL or similar -> skip
            skipped += 1
            print(f"  skip '{payload['title']}': {exc}")
            continue
        inserted += 1
        if evaluation:
            save_evaluation(job_id, evaluation, user_id)
        if status and status != "New":
            update_status(job_id, status, "", user_id)
        if followup_note:
            create_reminder(job_id, "follow_up", utc_now(), followup_note, user_id)
        print(f"  + '{payload['title']}' (job_id={job_id})")

    print(f"\nSeed complete: {inserted} jobs inserted, {skipped} skipped.")
    print(f"Database: {db_path()}")
    if not user:
        print(f"Login with {email} / {args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
