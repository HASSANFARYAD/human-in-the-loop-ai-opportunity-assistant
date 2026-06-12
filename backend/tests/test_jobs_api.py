from __future__ import annotations

import importlib
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> tuple[TestClient, dict]:
    db_path = tmp_path / "jobs.sqlite3"
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    from job_assistant.config import Environment, settings
    import api_server

    settings.db_path = str(db_path)
    settings.environment = Environment.DEV
    settings.database_url = None
    settings.rate_limits_enabled = False
    settings.scheduler_enabled = False
    settings.access_token_expire_minutes = 60
    settings.refresh_token_expire_days = 30
    settings.session_cookie_name = "job_assistant_refresh"
    settings.session_cookie_secure = False
    settings.session_cookie_samesite = "lax"
    settings.session_cookie_path = "/api/v1/auth"
    settings.cors_origins = "http://localhost:3000,http://localhost:3001"
    settings.cors_allow_credentials = True
    _create_minimal_schema(db_path)
    importlib.reload(api_server)
    client = TestClient(api_server.app)
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "jobs@example.com", "password": "StrongerPass123!", "full_name": "Jobs User"},
    )
    assert registered.status_code == 200
    return client, {"Authorization": f"Bearer {registered.json()['access_token']}"}


def _create_minimal_schema(db_path) -> None:
    with sqlite3.connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                owner_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(organization_id, slug)
            );
            CREATE TABLE workspace_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'viewer',
                status TEXT NOT NULL DEFAULT 'active',
                invited_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(workspace_id, user_id)
            );
            CREATE TABLE roles (
                name TEXT PRIMARY KEY,
                description TEXT,
                is_system INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE permissions (
                name TEXT PRIMARY KEY,
                description TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE role_permissions (
                role_name TEXT NOT NULL,
                permission_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(role_name, permission_name)
            );
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                workspace_id INTEGER,
                organization_id INTEGER,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                ip_address TEXT,
                user_agent TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                remote_type TEXT,
                url TEXT,
                source TEXT,
                date_received TEXT,
                description TEXT,
                recruiter_email TEXT,
                salary_min REAL,
                salary_max REAL,
                deadline TEXT,
                raw_text TEXT,
                opportunity_type TEXT DEFAULT 'job' NOT NULL,
                classification TEXT DEFAULT 'job',
                classification_reason TEXT,
                classification_confidence REAL,
                opportunity_confidence REAL,
                importable INTEGER DEFAULT 1,
                blocked_reason TEXT,
                source_type TEXT,
                source_name TEXT,
                source_url TEXT,
                source_email_id TEXT,
                source_email_open_url TEXT,
                parent_source_id TEXT,
                parent_source_title TEXT,
                extracted_from TEXT,
                raw_source_snippet TEXT,
                original_url TEXT,
                resolved_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, workspace_id, url)
            );
            CREATE TABLE profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                cv_text TEXT,
                target_roles TEXT,
                industries TEXT,
                locations TEXT,
                remote_preference TEXT,
                salary_expectations TEXT,
                work_authorization TEXT,
                years_experience TEXT,
                skills TEXT,
                deal_breakers TEXT,
                full_name TEXT,
                email TEXT,
                preferred_role TEXT,
                country TEXT,
                job_preferences TEXT,
                platforms TEXT,
                resume_name TEXT,
                integration_status TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE evaluations (
                job_id INTEGER PRIMARY KEY,
                match_score INTEGER,
                priority TEXT,
                skill_match INTEGER,
                title_match INTEGER,
                seniority_match INTEGER,
                location_match INTEGER,
                salary_match INTEGER,
                industry_match INTEGER,
                authorization_match INTEGER,
                deal_breaker_penalty INTEGER,
                good_fit TEXT,
                weak_areas TEXT,
                red_flags TEXT,
                opportunity_type TEXT DEFAULT 'job' NOT NULL,
                prize_value_score INTEGER,
                tech_alignment_score INTEGER,
                webinar_relevance_score INTEGER,
                generated_at TEXT NOT NULL
            );
            CREATE TABLE application_materials (
                job_id INTEGER PRIMARY KEY,
                professional_summary TEXT,
                cover_letter TEXT,
                resume_bullets TEXT,
                screening_answers TEXT,
                linkedin_message TEXT,
                why_fit TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE applications (
                job_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'New',
                notes TEXT,
                last_updated TEXT NOT NULL
            );
            CREATE TABLE reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                kind TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE resume_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                job_id INTEGER,
                review_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE interview_prep_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL,
                prep_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                job_id INTEGER,
                title TEXT,
                mime_type TEXT,
                data_url TEXT NOT NULL,
                duration_ms INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                interview_prep_session_id INTEGER,
                original_filename TEXT,
                stored_path TEXT,
                playback_url TEXT,
                file_size INTEGER,
                storage_type TEXT
            );
            """
        )


def _job_payload(title: str, opportunity_type: str) -> dict:
    return {
        "title": title,
        "company": "Example Co",
        "location": "Remote",
        "source": "Test",
        "description": "Job description with responsibilities, requirements, qualifications, salary, and apply now details.",
        "url": f"https://example.com/{title.lower().replace(' ', '-')}",
        "opportunity_type": opportunity_type,
        "classification": opportunity_type,
        "importable": True,
    }


def _seed_profile(user_id: int) -> None:
    from job_assistant.db import upsert_profile

    upsert_profile(
        {
            "cv_text": "Python FastAPI React TypeScript backend engineer",
            "target_roles": "Backend Engineer",
            "skills": "Python, FastAPI, React, TypeScript, SQL",
            "years_experience": "5",
        },
        user_id,
    )


def _mock_batch_scoring(monkeypatch, score_fn=None) -> None:
    import job_assistant.api as api

    monkeypatch.setattr(api.ai_orchestrator, "resolve_route", lambda *args, **kwargs: SimpleNamespace(source="fallback"))
    monkeypatch.setattr(
        api,
        "score_job",
        score_fn or (lambda profile, job, user_id=None: {"match_score": 82, "priority": "High", "good_fit": "Relevant", "weak_areas": "", "red_flags": ""}),
    )


def _mock_ai_json(monkeypatch, payload: dict | None = None) -> None:
    import job_assistant.api as api

    monkeypatch.setattr(api.ai_orchestrator, "resolve_route", lambda *args, **kwargs: SimpleNamespace(source="fallback"))
    monkeypatch.setattr(api.ai_orchestrator, "ask_json", lambda *args, **kwargs: payload or {})


def test_jobs_endpoint_defaults_to_job_like_content(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    user_id = get_user_by_email("jobs@example.com")["id"]
    insert_job(_job_payload("Backend Engineer", "job"), user_id)
    insert_job(_job_payload("Data Internship", "internship"), user_id)
    insert_job(_job_payload("Platform Contract", "contract"), user_id)
    insert_job(_job_payload("Freelance Builder", "freelance"), user_id)
    insert_job(_job_payload("AI Hackathon", "hackathon"), user_id)
    insert_job(_job_payload("Founder Webinar", "webinar"), user_id)

    default_response = client.get("/api/v1/jobs", headers=headers)
    assert default_response.status_code == 200
    default_types = {item["classification"] for item in default_response.json()}
    assert default_types == {"job", "internship", "contract", "freelance"}

    all_response = client.get("/api/v1/jobs", params={"content_type": "all"}, headers=headers)
    assert all_response.status_code == 200
    all_types = {item["classification"] for item in all_response.json()}
    assert {"hackathon", "webinar"}.issubset(all_types)


def test_delete_job_removes_related_rows(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import (
        create_reminder,
        get_user_by_email,
        insert_job,
        save_evaluation,
        save_interview_prep,
        save_materials,
        save_recording,
        save_resume_review,
    )

    user_id = get_user_by_email("jobs@example.com")["id"]
    job_id = insert_job(_job_payload("Delete Me", "job"), user_id)
    save_evaluation(job_id, {"match_score": 80, "priority": "High"}, user_id)
    save_materials(job_id, {"cover_letter": "Hello"}, user_id)
    create_reminder(job_id, "follow_up", "2000-01-01T00:00:00+00:00", "Check", user_id)
    save_resume_review(user_id, {"summary": "Review"}, job_id)
    save_interview_prep(user_id, job_id, {"summary": "Prep"})
    save_recording(user_id, {"title": "Recording", "mime_type": "audio/webm", "data_url": "data:audio/webm;base64,AA=="}, job_id)

    deleted = client.delete(f"/api/v1/jobs/{job_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["message"] == "Job deleted"

    with sqlite3.connect(tmp_path / "jobs.sqlite3") as con:
        for table in [
            "jobs",
            "evaluations",
            "application_materials",
            "applications",
            "reminders",
            "resume_reviews",
            "interview_prep_sessions",
            "recordings",
        ]:
            assert con.execute(f"SELECT COUNT(*) FROM {table} WHERE {'id' if table == 'jobs' else 'job_id'}=?", (job_id,)).fetchone()[0] == 0


def test_batch_scoring_score_all_unscored_targets_only_job_like_content(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    _mock_batch_scoring(monkeypatch)
    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)
    job_id = insert_job(_job_payload("Backend Engineer", "job"), user_id)
    internship_id = insert_job(_job_payload("Data Internship", "internship"), user_id)
    insert_job(_job_payload("AI Hackathon", "hackathon"), user_id)

    response = client.post("/api/v1/jobs/score-batch", json={"score_all_unscored": True}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_requested"] == 2
    assert body["scored"] == 2
    assert body["skipped"] == 0
    assert {item["job_id"] for item in body["results"]} == {job_id, internship_id}


def test_batch_scoring_skips_selected_non_job_content(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    _mock_batch_scoring(monkeypatch)
    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)
    job_id = insert_job(_job_payload("Backend Engineer", "job"), user_id)
    hackathon_id = insert_job(_job_payload("AI Hackathon", "hackathon"), user_id)

    response = client.post("/api/v1/jobs/score-batch", json={"job_ids": [job_id, hackathon_id]}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["scored"] == 1
    assert body["skipped"] == 1
    skipped = next(item for item in body["results"] if item["status"] == "skipped")
    assert skipped["job_id"] == hackathon_id
    assert "Only jobs" in skipped["reason"]


def test_batch_scoring_skips_jobs_missing_description(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    _mock_batch_scoring(monkeypatch)
    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)
    payload = _job_payload("No Description", "job")
    payload["description"] = ""
    payload["raw_text"] = ""
    job_id = insert_job(payload, user_id)

    response = client.post("/api/v1/jobs/score-batch", json={"job_ids": [job_id]}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["scored"] == 0
    assert body["skipped"] == 1
    assert body["results"][0]["reason"] == "Job description is missing."


def test_batch_scoring_continues_after_one_job_fails(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)
    ok_id = insert_job(_job_payload("Backend Engineer", "job"), user_id)
    fail_id = insert_job(_job_payload("Failing Engineer", "job"), user_id)

    def fake_score(profile, job, user_id=None):
        if int(job["id"]) == fail_id:
            raise RuntimeError("provider timeout")
        return {"match_score": 77, "priority": "High", "good_fit": "Relevant", "weak_areas": "", "red_flags": ""}

    _mock_batch_scoring(monkeypatch, fake_score)
    response = client.post("/api/v1/jobs/score-batch", json={"job_ids": [ok_id, fail_id]}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["scored"] == 1
    assert body["failed"] == 1
    failed = next(item for item in body["results"] if item["status"] == "failed")
    assert failed["job_id"] == fail_id
    assert failed["error"] == "provider timeout"


def test_batch_scoring_empty_unscored_jobs_returns_clear_error(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email

    _mock_batch_scoring(monkeypatch)
    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)

    response = client.post("/api/v1/jobs/score-batch", json={"score_all_unscored": True}, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "No unscored jobs are available for scoring."


def test_batch_scoring_missing_profile_returns_clear_error(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    _mock_batch_scoring(monkeypatch)
    user_id = get_user_by_email("jobs@example.com")["id"]
    job_id = insert_job(_job_payload("Backend Engineer", "job"), user_id)

    response = client.post("/api/v1/jobs/score-batch", json={"job_ids": [job_id]}, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Add your resume profile before scoring jobs."


def test_tailor_resume_requires_profile_context(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    _mock_ai_json(monkeypatch)
    user_id = get_user_by_email("jobs@example.com")["id"]
    job_id = insert_job(_job_payload("Backend Engineer", "job"), user_id)

    response = client.post(f"/api/v1/jobs/{job_id}/tailor-resume", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Add resume or profile details before tailoring a resume."


def test_tailor_resume_requires_job_description(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    _mock_ai_json(monkeypatch)
    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)
    payload = _job_payload("Backend Engineer", "job")
    payload["description"] = ""
    payload["raw_text"] = ""
    job_id = insert_job(payload, user_id)

    response = client.post(f"/api/v1/jobs/{job_id}/tailor-resume", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "This job does not have enough description detail to tailor a resume."


def test_tailor_resume_returns_structured_resume_sections(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email, insert_job

    _mock_ai_json(
        monkeypatch,
        {
            "tailored_summary": "Backend engineer with FastAPI experience.",
            "tailored_experience_bullets": ["Built APIs with FastAPI."],
            "skills_to_emphasize": ["Python", "FastAPI"],
            "keywords_to_include": ["Backend", "API"],
            "resume_draft": "Professional Summary\nBackend engineer with FastAPI experience.",
        },
    )
    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)
    job_id = insert_job(_job_payload("Backend Engineer", "job"), user_id)

    response = client.post(f"/api/v1/jobs/{job_id}/tailor-resume", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "tailored_resume"
    assert body["tailored_summary"] == "Backend engineer with FastAPI experience."
    assert body["tailored_experience_bullets"] == ["Built APIs with FastAPI."]
    assert body["resume_draft"].startswith("Professional Summary")


def test_find_jobs_from_profile_filters_non_job_content_and_scores(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    from job_assistant.db import get_user_by_email
    import job_assistant.api as api

    user_id = get_user_by_email("jobs@example.com")["id"]
    _seed_profile(user_id)
    monkeypatch.setattr(
        api,
        "discover_public_opportunities",
        lambda query, sources, limit_per_source: [
            _job_payload("Backend Engineer", "job"),
            _job_payload("AI Hackathon", "hackathon"),
        ],
    )
    _mock_batch_scoring(monkeypatch)

    response = client.post("/api/v1/discovery/from-profile", json={"limit_per_source": 5}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["found"] == 1
    assert body["scored"] == 1
    assert body["opportunities"][0]["classification"] == "job"
    assert body["opportunities"][0]["match_score"] == 82
    assert "Backend" in body["query"]


def test_find_jobs_from_profile_requires_profile_context(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)

    response = client.post("/api/v1/discovery/from-profile", json={}, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Add resume or profile details before finding jobs."
