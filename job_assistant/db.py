from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

DEFAULT_DB_PATH = os.getenv("APP_DB_PATH", "data/job_assistant.sqlite3")
STATUSES = ["New", "Reviewed", "Apply manually", "Applied", "Interview", "Rejected", "Offer", "Archived", "Skip"]
OPPORTUNITY_TYPES = ["job", "hackathon", "competition", "webinar", "other"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    path = Path(os.getenv("APP_DB_PATH", DEFAULT_DB_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect(path: Optional[str | Path] = None):
    con = sqlite3.connect(path or db_path())
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _run_migrations(con) -> None:
    """Run schema migrations for existing databases"""
    cursor = con.execute("PRAGMA table_info(jobs)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'opportunity_type' not in columns:
        con.execute("ALTER TABLE jobs ADD COLUMN opportunity_type TEXT DEFAULT 'job' NOT NULL")

    cursor = con.execute("PRAGMA table_info(evaluations)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'opportunity_type' not in columns:
        con.execute("ALTER TABLE evaluations ADD COLUMN opportunity_type TEXT DEFAULT 'job' NOT NULL")
    if 'prize_value_score' not in columns:
        con.execute("ALTER TABLE evaluations ADD COLUMN prize_value_score INTEGER")
    if 'tech_alignment_score' not in columns:
        con.execute("ALTER TABLE evaluations ADD COLUMN tech_alignment_score INTEGER")
    if 'webinar_relevance_score' not in columns:
        con.execute("ALTER TABLE evaluations ADD COLUMN webinar_relevance_score INTEGER")


def init_db() -> None:
    with connect() as con:
        con.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
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
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                remote_type TEXT,
                url TEXT UNIQUE,
                source TEXT,
                date_received TEXT,
                description TEXT,
                recruiter_email TEXT,
                salary_min REAL,
                salary_max REAL,
                deadline TEXT,
                raw_text TEXT,
                opportunity_type TEXT DEFAULT 'job' NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evaluations (
                job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
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

            CREATE TABLE IF NOT EXISTS application_materials (
                job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                professional_summary TEXT,
                cover_letter TEXT,
                resume_bullets TEXT,
                screening_answers TEXT,
                linkedin_message TEXT,
                why_fit TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS applications (
                job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'New',
                notes TEXT,
                last_updated TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        _run_migrations(con)


def upsert_profile(profile: Dict[str, Any]) -> None:
    fields = ["cv_text", "target_roles", "industries", "locations", "remote_preference", "salary_expectations", "work_authorization", "years_experience", "skills", "deal_breakers"]
    values = {k: profile.get(k, "") for k in fields}
    values["updated_at"] = utc_now()
    with connect() as con:
        con.execute(
            f"""
            INSERT INTO profile (id, {', '.join(values.keys())}) VALUES (1, {', '.join(['?'] * len(values))})
            ON CONFLICT(id) DO UPDATE SET {', '.join([f'{k}=excluded.{k}' for k in values.keys()])}
            """,
            list(values.values()),
        )


def get_profile() -> Dict[str, Any]:
    with connect() as con:
        row = con.execute("SELECT * FROM profile WHERE id=1").fetchone()
        return dict(row) if row else {}


def insert_job(job: Dict[str, Any]) -> int:
    now = utc_now()
    opportunity_type = str(job.get("opportunity_type") or "job").lower()
    if opportunity_type not in OPPORTUNITY_TYPES:
        opportunity_type = "other"
    payload = {
        "title": job.get("title") or "Untitled role",
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
        "created_at": now,
        "updated_at": now,
    }
    cols = list(payload.keys())
    with connect() as con:
        try:
            cur = con.execute(
                f"INSERT INTO jobs ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
                [payload[c] for c in cols],
            )
            job_id = int(cur.lastrowid)
            con.execute("INSERT OR IGNORE INTO applications(job_id, status, notes, last_updated) VALUES (?, 'New', '', ?)", (job_id, now))
            return job_id
        except sqlite3.IntegrityError:
            row = con.execute("SELECT id FROM jobs WHERE url = ?", (payload["url"],)).fetchone()
            return int(row["id"])


def list_jobs() -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            """
            SELECT j.*, a.status, a.notes, e.match_score, e.priority,
                   m.cover_letter, m.screening_answers
            FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            LEFT JOIN evaluations e ON e.job_id = j.id
            LEFT JOIN application_materials m ON m.job_id = j.id
            ORDER BY COALESCE(e.match_score, -1) DESC, j.updated_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_job(job_id: int) -> dict[str, Any]:
    with connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else {}


def save_evaluation(job_id: int, evaluation: Dict[str, Any]) -> None:
    now = utc_now()
    cols = [
        "job_id",
        "match_score",
        "priority",
        "skill_match",
        "title_match",
        "seniority_match",
        "location_match",
        "salary_match",
        "industry_match",
        "authorization_match",
        "deal_breaker_penalty",
        "good_fit",
        "weak_areas",
        "red_flags",
        "opportunity_type",
        "prize_value_score",
        "tech_alignment_score",
        "webinar_relevance_score",
        "generated_at",
    ]
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
        "good_fit": evaluation.get("good_fit", ""),
        "weak_areas": evaluation.get("weak_areas", ""),
        "red_flags": evaluation.get("red_flags", ""),
        "opportunity_type": evaluation.get("opportunity_type", "job"),
        "prize_value_score": evaluation.get("prize_value_score"),
        "tech_alignment_score": evaluation.get("tech_alignment_score"),
        "webinar_relevance_score": evaluation.get("webinar_relevance_score") or evaluation.get("topic_relevance"),
        "generated_at": now,
    }
    with connect() as con:
        con.execute(
            f"INSERT OR REPLACE INTO evaluations ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
            [values[c] for c in cols],
        )


def get_evaluation(job_id: int) -> dict[str, Any]:
    with connect() as con:
        row = con.execute("SELECT * FROM evaluations WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else {}


def save_materials(job_id: int, materials: Dict[str, Any]) -> None:
    now = utc_now()
    cols = ["job_id", "professional_summary", "cover_letter", "resume_bullets", "screening_answers", "linkedin_message", "why_fit", "updated_at"]
    values = {
        "job_id": job_id,
        "professional_summary": materials.get("professional_summary", ""),
        "cover_letter": materials.get("cover_letter", ""),
        "resume_bullets": materials.get("resume_bullets", ""),
        "screening_answers": materials.get("screening_answers", ""),
        "linkedin_message": materials.get("linkedin_message", ""),
        "why_fit": materials.get("why_fit", ""),
        "updated_at": now,
    }
    with connect() as con:
        con.execute(
            f"INSERT OR REPLACE INTO application_materials ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
            [values[c] for c in cols],
        )


def get_materials(job_id: int) -> dict[str, Any]:
    with connect() as con:
        row = con.execute("SELECT * FROM application_materials WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else {}


def update_status(job_id: int, status: str, notes: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    with connect() as con:
        con.execute(
            "INSERT INTO applications(job_id,status,notes,last_updated) VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, notes=excluded.notes, last_updated=excluded.last_updated",
            (job_id, status, notes, utc_now()),
        )


def create_reminder(job_id: int, kind: str, remind_at: str, note: str) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO reminders(job_id, kind, remind_at, note, created_at) VALUES (?,?,?,?,?)",
            (job_id, kind, remind_at, note, utc_now()),
        )


def due_reminders() -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            """
            SELECT r.*, j.title, j.company FROM reminders r
            LEFT JOIN jobs j ON j.id = r.job_id
            WHERE r.done = 0 AND r.remind_at <= ?
            ORDER BY r.remind_at ASC
            """,
            (utc_now(),),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_all_data() -> None:
    ALLOWED_TABLES = ["reminders", "application_materials", "evaluations", "applications", "jobs", "profile"]
    with connect() as con:
        for table in ALLOWED_TABLES:
            con.execute(f"DELETE FROM {table}")
