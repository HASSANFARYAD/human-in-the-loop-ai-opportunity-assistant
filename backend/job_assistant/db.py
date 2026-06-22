from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from job_assistant.config import settings
DEFAULT_DB_PATH = settings.db_path
from job_assistant.crypto import decrypt_text, encrypt_text

STATUSES = ["New", "Reviewed", "Needs Review", "Non-Opportunity", "Apply manually", "Applied", "Interview", "Rejected", "Offer", "Archived", "Skip"]
OPPORTUNITY_TYPES = ["job", "internship", "contract", "freelance", "hackathon", "competition", "grant", "scholarship", "webinar", "event", "newsletter", "blog_post", "marketing_email", "announcement", "unknown", "other"]
JOB_LIKE_TYPES = ("job", "internship", "contract", "freelance")
DEFAULT_USER_EMAIL = "local@example.com"
DEFAULT_LOCAL_PASSWORD = os.getenv("LOCAL_USER_PASSWORD", "ChangeMe123!")
PASSWORD_HASH_ITERATIONS = 600_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    path = Path(os.getenv("APP_DB_PATH", DEFAULT_DB_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect(path: Optional[str | Path] = None):
    con = sqlite3.connect(path or db_path(), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _run_migrations(con) -> None:
    """Run schema migrations for existing databases"""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_settings (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            service TEXT NOT NULL,
            api_key TEXT,
            config_json TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, service)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            ip_address TEXT,
            user_agent TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            enabled INTEGER NOT NULL DEFAULT 0,
            gmail_enabled INTEGER NOT NULL DEFAULT 1,
            public_sources_enabled INTEGER NOT NULL DEFAULT 1,
            linkedin_api_enabled INTEGER NOT NULL DEFAULT 0,
            score_new INTEGER NOT NULL DEFAULT 1,
            generate_materials INTEGER NOT NULL DEFAULT 0,
            gmail_interval_minutes INTEGER NOT NULL DEFAULT 30,
            public_interval_hours INTEGER NOT NULL DEFAULT 6,
            linkedin_interval_hours INTEGER NOT NULL DEFAULT 6,
            daily_summary_hour INTEGER NOT NULL DEFAULT 8,
            notify_in_app INTEGER NOT NULL DEFAULT 1,
            min_score_for_materials INTEGER NOT NULL DEFAULT 70,
            updated_at TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            level TEXT NOT NULL DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            read_at TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            attachment_url TEXT,
            page_url TEXT,
            user_agent TEXT,
            app_version TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            ip_address TEXT,
            user_agent TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            provider_name TEXT NOT NULL,
            auth_type TEXT NOT NULL DEFAULT 'api_key',
            encrypted_credentials TEXT,
            config_json TEXT,
            priority INTEGER NOT NULL DEFAULT 100,
            is_active INTEGER NOT NULL DEFAULT 1,
            health_status TEXT NOT NULL DEFAULT 'unknown',
            last_health_check_at TEXT,
            last_success_at TEXT,
            last_failure_at TEXT,
            failure_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, platform, provider_name)
        )
        """
    )

    con.execute("""
        CREATE TABLE IF NOT EXISTS ai_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            provider TEXT,
            model TEXT,
            task_type TEXT NOT NULL DEFAULT 'general',
            prompt_version TEXT,
            prompt_hash TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0,
            latency_ms INTEGER,
            status TEXT NOT NULL DEFAULT 'unknown',
            error_message TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT,
            template TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(name, version)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            trigger_event TEXT NOT NULL,
            action_type TEXT NOT NULL,
            conditions_json TEXT,
            action_config_json TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            human_approval_required INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS automation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER REFERENCES automation_rules(id) ON DELETE SET NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending',
            trigger_event TEXT NOT NULL,
            input_payload TEXT,
            output_payload TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS automation_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE,
            step_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            output_json TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS automation_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER REFERENCES automation_runs(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            error_type TEXT,
            error_message TEXT NOT NULL,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            description TEXT,
            applied_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS usage_counters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ip_address TEXT,
            resource_type TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            window_start TEXT NOT NULL,
            window_end TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, ip_address, resource_type, window_start)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_usage_counters_window ON usage_counters(resource_type, window_end)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS system_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_type TEXT NOT NULL DEFAULT 'counter',
            value REAL NOT NULL DEFAULT 0,
            labels_json TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_system_metrics_name_time ON system_metrics(metric_name, created_at)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS alert_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            severity TEXT NOT NULL DEFAULT 'warning',
            title TEXT NOT NULL,
            message TEXT,
            source TEXT NOT NULL DEFAULT 'system',
            metadata_json TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            acknowledged_at TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_alert_events_status_time ON alert_events(status, created_at)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_name TEXT NOT NULL DEFAULT 'default',
            job_type TEXT NOT NULL,
            payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            locked_at TEXT,
            locked_by TEXT,
            run_after TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_worker_jobs_ready ON worker_jobs(status, queue_name, run_after)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS compliance_exports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workspace_id INTEGER,
            export_type TEXT NOT NULL DEFAULT 'user_data',
            status TEXT NOT NULL DEFAULT 'completed',
            file_path TEXT NOT NULL,
            expires_at TEXT,
            created_at TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(organization_id, slug)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'viewer',
            status TEXT NOT NULL DEFAULT 'active',
            invited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(workspace_id, user_id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            name TEXT PRIMARY KEY,
            description TEXT,
            is_system INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            name TEXT PRIMARY KEY,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
            permission_name TEXT NOT NULL REFERENCES permissions(name) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY(role_name, permission_name)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS shared_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            access_level TEXT NOT NULL DEFAULT 'read',
            created_at TEXT NOT NULL,
            expires_at TEXT,
            UNIQUE(workspace_id, resource_type, resource_id)
        )
    """)
    _ensure_default_user(con)
    _seed_roles_permissions(con)
    _migrate_audit_scope_columns(con)
    _ensure_personal_workspace_for_all_users(con)
    _migrate_profile_table(con)
    _ensure_profile_columns(con)
    _migrate_profile_multi(con)
    _migrate_jobs_table(con)
    _ensure_workspace_scope_columns(con)
    _rebuild_jobs_workspace_unique(con)
    _rebuild_workspace_unique_tables(con)


    cursor = con.execute("PRAGMA table_info(automation_preferences)")
    automation_columns = {row[1] for row in cursor.fetchall()}
    if "linkedin_api_enabled" not in automation_columns:
        con.execute("ALTER TABLE automation_preferences ADD COLUMN linkedin_api_enabled INTEGER NOT NULL DEFAULT 0")
    if "linkedin_interval_hours" not in automation_columns:
        con.execute("ALTER TABLE automation_preferences ADD COLUMN linkedin_interval_hours INTEGER NOT NULL DEFAULT 6")

    cursor = con.execute("PRAGMA table_info(jobs)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'opportunity_type' not in columns:
        con.execute("ALTER TABLE jobs ADD COLUMN opportunity_type TEXT DEFAULT 'job' NOT NULL")
    for column, definition in {
        "classification": "TEXT DEFAULT 'job'",
        "classification_reason": "TEXT",
        "classification_confidence": "REAL",
        "opportunity_confidence": "REAL",
        "importable": "INTEGER DEFAULT 1",
        "blocked_reason": "TEXT",
        "source_type": "TEXT",
        "source_name": "TEXT",
        "source_url": "TEXT",
        "source_email_id": "TEXT",
        "source_email_open_url": "TEXT",
        "parent_source_id": "TEXT",
        "parent_source_title": "TEXT",
        "extracted_from": "TEXT",
        "raw_source_snippet": "TEXT",
        "original_url": "TEXT",
        "resolved_url": "TEXT",
    }.items():
        if column not in columns:
            con.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")

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

    cursor = con.execute("PRAGMA table_info(recordings)")
    recording_columns = {row[1] for row in cursor.fetchall()}
    for column, definition in {
        "interview_prep_session_id": "INTEGER",
        "original_filename": "TEXT",
        "stored_path": "TEXT",
        "playback_url": "TEXT",
        "file_size": "INTEGER",
        "storage_type": "TEXT",
    }.items():
        if column not in recording_columns:
            con.execute(f"ALTER TABLE recordings ADD COLUMN {column} {definition}")
    con.execute("CREATE INDEX IF NOT EXISTS idx_recordings_user_job ON recordings(user_id, job_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_resume_reviews_user_job ON resume_reviews(user_id, job_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_interview_prep_user_job ON interview_prep_sessions(user_id, job_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_gmail_messages_user_message ON gmail_messages(user_id, message_id)")
    _rebuild_legacy_job_child_tables(con)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("DELETE FROM applications WHERE job_id NOT IN (SELECT id FROM jobs)")
        con.execute("DELETE FROM evaluations WHERE job_id NOT IN (SELECT id FROM jobs)")
        con.execute("DELETE FROM application_materials WHERE job_id NOT IN (SELECT id FROM jobs)")
        con.execute("DELETE FROM resume_reviews WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)")
        con.execute("DELETE FROM interview_prep_sessions WHERE job_id NOT IN (SELECT id FROM jobs)")
        con.execute("DELETE FROM recordings WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs)")
    finally:
        con.execute("PRAGMA foreign_keys=ON")


def _ensure_default_user(con) -> int:
    row = con.execute("SELECT id FROM users WHERE email=?", (DEFAULT_USER_EMAIL,)).fetchone()
    if row:
        user_id = int(row["id"])
        password_hash = con.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()["password_hash"]
        if str(password_hash).startswith("legacy:"):
            con.execute(
                "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                (_hash_default_password(DEFAULT_LOCAL_PASSWORD), utc_now(), user_id),
            )
        return user_id
    now = utc_now()
    cur = con.execute(
        "INSERT INTO users(email, password_hash, full_name, created_at, updated_at) VALUES (?,?,?,?,?)",
        (DEFAULT_USER_EMAIL, _hash_default_password(DEFAULT_LOCAL_PASSWORD), "Local User", now, now),
    )
    return int(cur.lastrowid)


def _hash_default_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_HASH_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest.hex()}"


def _table_columns(con, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}




def _add_column_if_missing(con, table: str, column: str, definition: str) -> None:
    if column not in _table_columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _rebuild_legacy_job_child_tables(con) -> None:
    legacy = con.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE '%jobs_legacy%'").fetchall()
    if not legacy:
        return
    con.execute("PRAGMA foreign_keys=OFF")
    table_sql = {
        "applications": """
            CREATE TABLE applications (
                job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'New',
                notes TEXT,
                last_updated TEXT NOT NULL
            )
        """,
        "evaluations": """
            CREATE TABLE evaluations (
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
                generated_at TEXT NOT NULL,
                opportunity_type TEXT DEFAULT 'job' NOT NULL,
                prize_value_score INTEGER,
                tech_alignment_score INTEGER,
                webinar_relevance_score INTEGER
            )
        """,
        "application_materials": """
            CREATE TABLE application_materials (
                job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                professional_summary TEXT,
                cover_letter TEXT,
                resume_bullets TEXT,
                screening_answers TEXT,
                linkedin_message TEXT,
                why_fit TEXT,
                updated_at TEXT NOT NULL
            )
        """,
        "reminders": """
            CREATE TABLE reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT NOT NULL
            )
        """,
    }
    for table, create_sql in table_sql.items():
        row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=? AND sql LIKE '%jobs_legacy%'", (table,)).fetchone()
        if not row:
            continue
        columns = [col for col in _table_columns(con, table)]
        con.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy_fk")
        con.execute(create_sql)
        common = [col for col in columns if col in _table_columns(con, table)]
        con.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(common)}) SELECT {','.join(common)} FROM {table}_legacy_fk WHERE job_id IN (SELECT id FROM jobs)"
        )
        con.execute(f"DROP TABLE {table}_legacy_fk")


def _workspace_scope_for_user(con, user_id: int, workspace_id: int | None = None) -> tuple[int, int]:
    """Resolve and authorize a workspace/organization scope for user-owned data.

    If workspace_id is omitted, the user's personal workspace is created/used.
    If supplied, the user must be an active workspace member.
    """
    _seed_roles_permissions(con)
    user = con.execute("SELECT id, email, full_name FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        raise ValueError("User not found")
    if workspace_id is None:
        ws = _ensure_personal_workspace(con, user_id, user["email"], user["full_name"] or "")
        return int(ws["workspace_id"]), int(ws["organization_id"])
    row = con.execute(
        """
        SELECT w.id AS workspace_id, w.organization_id
        FROM workspaces w
        JOIN workspace_members wm ON wm.workspace_id = w.id
        WHERE w.id=? AND wm.user_id=? AND wm.status='active'
        """,
        (workspace_id, user_id),
    ).fetchone()
    if not row:
        raise PermissionError("You do not have access to this workspace")
    return int(row["workspace_id"]), int(row["organization_id"])


def _ensure_workspace_scope_columns(con) -> None:
    """Add workspace/org ownership columns to core resource tables and backfill them."""
    scoped_tables = [
        "jobs",
        "feedback",
        "integration_settings",
        "provider_configs",
        "ai_generations",
        "automation_rules",
        "automation_runs",
        "automation_errors",
    ]
    for table in scoped_tables:
        _add_column_if_missing(con, table, "workspace_id", "INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
        _add_column_if_missing(con, table, "organization_id", "INTEGER REFERENCES organizations(id) ON DELETE CASCADE")

    # Publishing resources were planned but not yet implemented. Add a minimal
    # workspace-aware publishing schema now so generated posts have a proper home.
    con.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            title TEXT,
            base_content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            scheduled_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS post_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            provider_name TEXT,
            transformed_content TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            published_url TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    users = con.execute("SELECT id, email, full_name FROM users").fetchall()
    for user in users:
        ws = _ensure_personal_workspace(con, int(user["id"]), user["email"], user["full_name"] or "")
        workspace_id = int(ws["workspace_id"])
        organization_id = int(ws["organization_id"])
        for table in scoped_tables:
            con.execute(
                f"UPDATE {table} SET workspace_id=COALESCE(workspace_id, ?), organization_id=COALESCE(organization_id, ?) WHERE user_id=?",
                (workspace_id, organization_id, int(user["id"])),
            )




def _rebuild_jobs_workspace_unique(con) -> None:
    markers = {row["version"] for row in con.execute("SELECT version FROM schema_migrations").fetchall()}
    if "20260525_workspace_unique_jobs" in markers:
        return
    if "jobs" in {row["name"] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
        current_columns = _table_columns(con, "jobs")
        if {"workspace_id", "organization_id"}.issubset(current_columns):
            now = utc_now()
            con.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?,?,?)",
                ("20260525_workspace_unique_jobs", "Workspace scoped opportunity unique constraint", now),
            )
            return
    now = utc_now()
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("ALTER TABLE jobs RENAME TO jobs_legacy_ws")
    con.execute("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, workspace_id, url)
        )
    """)
    con.execute("""
        INSERT OR REPLACE INTO jobs(
            id, user_id, workspace_id, organization_id, title, company, location, remote_type, url, source,
            date_received, description, recruiter_email, salary_min, salary_max, deadline, raw_text,
            opportunity_type, created_at, updated_at
        )
        SELECT id, user_id, workspace_id, organization_id, title, company, location, remote_type, url, source,
               date_received, description, recruiter_email, salary_min, salary_max, deadline, raw_text,
               opportunity_type, created_at, updated_at
        FROM jobs_legacy_ws
    """)
    con.execute("DROP TABLE jobs_legacy_ws")
    con.execute("INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?,?,?)", ("20260525_workspace_unique_jobs", "Workspace scoped opportunity unique constraint", now))
    con.execute("PRAGMA foreign_keys=ON")


def _rebuild_workspace_unique_tables(con) -> None:
    """Rebuild unique constraints so integrations/providers can vary per workspace."""
    markers = {row["version"] for row in con.execute("SELECT version FROM schema_migrations").fetchall()} if "schema_migrations" in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()} else set()
    now = utc_now()
    if "20260525_workspace_unique_integration_settings" not in markers:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("ALTER TABLE integration_settings RENAME TO integration_settings_legacy_ws")
        con.execute("""
            CREATE TABLE integration_settings (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                service TEXT NOT NULL,
                api_key TEXT,
                config_json TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id, workspace_id, service)
            )
        """)
        legacy_cols = _table_columns(con, "integration_settings_legacy_ws")
        ws_expr = "workspace_id" if "workspace_id" in legacy_cols else "NULL"
        org_expr = "organization_id" if "organization_id" in legacy_cols else "NULL"
        con.execute(f"""
            INSERT OR REPLACE INTO integration_settings(user_id, workspace_id, organization_id, service, api_key, config_json, updated_at)
            SELECT user_id, {ws_expr}, {org_expr}, service, api_key, config_json, updated_at FROM integration_settings_legacy_ws
        """)
        con.execute("DROP TABLE integration_settings_legacy_ws")
        _ensure_workspace_scope_columns(con)
        con.execute("INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?,?,?)", ("20260525_workspace_unique_integration_settings", "Workspace scoped integration_settings primary key", now))
        con.execute("PRAGMA foreign_keys=ON")

    markers = {row["version"] for row in con.execute("SELECT version FROM schema_migrations").fetchall()}
    if "20260525_workspace_unique_provider_configs" not in markers:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("ALTER TABLE provider_configs RENAME TO provider_configs_legacy_ws")
        con.execute("""
            CREATE TABLE provider_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                platform TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                auth_type TEXT NOT NULL DEFAULT 'api_key',
                encrypted_credentials TEXT,
                config_json TEXT,
                priority INTEGER NOT NULL DEFAULT 100,
                is_active INTEGER NOT NULL DEFAULT 1,
                health_status TEXT NOT NULL DEFAULT 'unknown',
                last_health_check_at TEXT,
                last_success_at TEXT,
                last_failure_at TEXT,
                failure_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, workspace_id, platform, provider_name)
            )
        """)
        legacy_cols = _table_columns(con, "provider_configs_legacy_ws")
        ws_expr = "workspace_id" if "workspace_id" in legacy_cols else "NULL"
        org_expr = "organization_id" if "organization_id" in legacy_cols else "NULL"
        con.execute(f"""
            INSERT OR REPLACE INTO provider_configs(
                id, user_id, workspace_id, organization_id, platform, provider_name, auth_type, encrypted_credentials,
                config_json, priority, is_active, health_status, last_health_check_at, last_success_at, last_failure_at,
                failure_count, success_count, latency_ms, last_error, created_at, updated_at
            )
            SELECT id, user_id, {ws_expr}, {org_expr}, platform, provider_name, auth_type, encrypted_credentials,
                   config_json, priority, is_active, health_status, last_health_check_at, last_success_at, last_failure_at,
                   failure_count, success_count, latency_ms, last_error, created_at, updated_at
            FROM provider_configs_legacy_ws
        """)
        con.execute("DROP TABLE provider_configs_legacy_ws")
        _ensure_workspace_scope_columns(con)
        con.execute("INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES (?,?,?)", ("20260525_workspace_unique_provider_configs", "Workspace scoped provider_configs unique constraint", now))
        con.execute("PRAGMA foreign_keys=ON")


def _migrate_profile_table(con) -> None:
    columns = _table_columns(con, "profile")
    if "user_id" in columns and "id" in columns:
        return

    default_user_id = _ensure_default_user(con)
    legacy_rows = con.execute("SELECT * FROM profile").fetchall() if columns else []
    con.execute("ALTER TABLE profile RENAME TO profile_legacy")
    con.execute(
        """
        CREATE TABLE profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
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
        )
        """
    )
    for row in legacy_rows[:1]:
        con.execute(
            """
            INSERT INTO profile(
                user_id, cv_text, target_roles, industries, locations, remote_preference,
                salary_expectations, work_authorization, years_experience, skills,
                deal_breakers, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                default_user_id,
                row["cv_text"],
                row["target_roles"],
                row["industries"],
                row["locations"],
                row["remote_preference"],
                row["salary_expectations"],
                row["work_authorization"],
                row["years_experience"],
                row["skills"],
                row["deal_breakers"],
                row["updated_at"],
            ),
        )
    con.execute("DROP TABLE profile_legacy")


def _migrate_profile_multi(con) -> None:
    """Allow multiple profiles per user by dropping the UNIQUE(user_id) constraint
    and adding name/is_default. Existing single profiles become the named 'Default'."""
    columns = _table_columns(con, "profile")
    if not columns or "is_default" in columns:
        return  # not yet created, or already migrated

    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("ALTER TABLE profile RENAME TO profile_legacy")
    con.execute(
        """
        CREATE TABLE profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT 'Default',
            is_default INTEGER NOT NULL DEFAULT 0,
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
            created_at TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
        """
    )
    legacy_cols = _table_columns(con, "profile_legacy")
    new_cols = _table_columns(con, "profile")
    copy_cols = [c for c in legacy_cols if c in new_cols and c not in ("name", "is_default")]
    col_list = ", ".join(copy_cols)
    con.execute(
        f"INSERT INTO profile ({col_list}, name, is_default) SELECT {col_list}, 'Default', 1 FROM profile_legacy"
    )
    con.execute("DROP TABLE profile_legacy")
    con.execute("PRAGMA foreign_keys = ON")


def _ensure_profile_columns(con) -> None:
    extra_columns = {
        "full_name": "TEXT",
        "email": "TEXT",
        "preferred_role": "TEXT",
        "country": "TEXT",
        "job_preferences": "TEXT",
        "platforms": "TEXT",
        "resume_name": "TEXT",
        "integration_status": "TEXT",
    }
    for column, definition in extra_columns.items():
        _add_column_if_missing(con, "profile", column, definition)


def _migrate_jobs_table(con) -> None:
    columns = _table_columns(con, "jobs")
    if "user_id" in columns:
        return

    default_user_id = _ensure_default_user(con)
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("ALTER TABLE jobs RENAME TO jobs_legacy")
    con.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, url)
        )
        """
    )
    legacy_cols = _table_columns(con, "jobs_legacy")
    opportunity_expr = "opportunity_type" if "opportunity_type" in legacy_cols else "'job'"
    con.execute(
        f"""
        INSERT INTO jobs(
            id, user_id, title, company, location, remote_type, url, source,
            date_received, description, recruiter_email, salary_min, salary_max,
            deadline, raw_text, opportunity_type, created_at, updated_at
        )
        SELECT
            id, ?, title, company, location, remote_type, url, source,
            date_received, description, recruiter_email, salary_min, salary_max,
            deadline, raw_text, {opportunity_expr}, created_at, updated_at
        FROM jobs_legacy
        """,
        (default_user_id,),
    )
    con.execute("DROP TABLE jobs_legacy")
    con.execute("PRAGMA foreign_keys = ON")


def init_db() -> None:
    with connect() as con:
        con.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
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

            CREATE TABLE IF NOT EXISTS resume_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
                review_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interview_prep_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                prep_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
                title TEXT,
                mime_type TEXT,
                data_url TEXT NOT NULL,
                duration_ms INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gmail_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                message_id TEXT,
                thread_id TEXT,
                sender TEXT,
                subject TEXT,
                date TEXT,
                snippet TEXT,
                open_url TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, url)
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

            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                ip_address TEXT,
                user_agent TEXT
            );

            CREATE TABLE IF NOT EXISTS automation_preferences (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                enabled INTEGER NOT NULL DEFAULT 0,
                gmail_enabled INTEGER NOT NULL DEFAULT 1,
                public_sources_enabled INTEGER NOT NULL DEFAULT 1,
                linkedin_api_enabled INTEGER NOT NULL DEFAULT 0,
                score_new INTEGER NOT NULL DEFAULT 1,
                generate_materials INTEGER NOT NULL DEFAULT 0,
                gmail_interval_minutes INTEGER NOT NULL DEFAULT 30,
                public_interval_hours INTEGER NOT NULL DEFAULT 6,
                linkedin_interval_hours INTEGER NOT NULL DEFAULT 6,
                daily_summary_hour INTEGER NOT NULL DEFAULT 8,
                notify_in_app INTEGER NOT NULL DEFAULT 1,
                min_score_for_materials INTEGER NOT NULL DEFAULT 70,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                level TEXT NOT NULL DEFAULT 'info',
                title TEXT NOT NULL,
                message TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                read_at TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'open',
                attachment_url TEXT,
                page_url TEXT,
                user_agent TEXT,
                app_version TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS score_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                workspace_id INTEGER,
                job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
                signal TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                ip_address TEXT,
                user_agent TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        _run_migrations(con)


def create_user(email: str, password_hash: str, full_name: str = "") -> int:
    now = utc_now()
    with connect() as con:
        cur = con.execute(
            "INSERT INTO users(email, password_hash, full_name, created_at, updated_at) VALUES (?,?,?,?,?)",
            (email.strip().lower(), password_hash, full_name.strip(), now, now),
        )
        return int(cur.lastrowid)


def get_user_by_email(email: str) -> dict[str, Any]:
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
        return dict(row) if row else {}


def get_user(user_id: int) -> dict[str, Any]:
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
        return dict(row) if row else {}


PROFILE_FIELDS = [
    "cv_text",
    "target_roles",
    "industries",
    "locations",
    "remote_preference",
    "salary_expectations",
    "work_authorization",
    "years_experience",
    "skills",
    "deal_breakers",
    "full_name",
    "email",
    "preferred_role",
    "country",
    "job_preferences",
    "platforms",
    "resume_name",
    "integration_status",
]


def _default_profile_id(con, user_id: int) -> int | None:
    row = con.execute(
        "SELECT id FROM profile WHERE user_id=? ORDER BY is_default DESC, id ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    return int(row["id"]) if row else None


def upsert_profile(profile: Dict[str, Any], user_id: int = 1, profile_id: int | None = None) -> int:
    """Update an existing profile (the default, or the one identified by profile_id),
    or create the user's first profile. Returns the profile id."""
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    with connect() as con:
        target_id = profile_id or _default_profile_id(con, user_id)
        if target_id is not None:
            assignments = ", ".join(f"{k}=?" for k in values.keys())
            con.execute(
                f"UPDATE profile SET {assignments}, updated_at=? WHERE id=? AND user_id=?",
                [*values.values(), now, target_id, user_id],
            )
            return int(target_id)
        # First profile for this user -> create it as the default.
        name = (profile.get("name") or "Default").strip() or "Default"
        cur = con.execute(
            f"INSERT INTO profile (user_id, name, is_default, {', '.join(values.keys())}, created_at, updated_at) "
            f"VALUES (?, ?, 1, {', '.join(['?'] * len(values))}, ?, ?)",
            [user_id, name, *values.values(), now, now],
        )
        return int(cur.lastrowid)


def create_profile(user_id: int, profile: Dict[str, Any], name: str = "", make_default: bool = False) -> int:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    clean_name = (name or profile.get("name") or "").strip() or "New profile"
    with connect() as con:
        has_any = con.execute("SELECT 1 FROM profile WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
        is_default = 1 if (make_default or not has_any) else 0
        # Ensure unique name per user.
        base, suffix = clean_name, 2
        while con.execute("SELECT 1 FROM profile WHERE user_id=? AND name=?", (user_id, clean_name)).fetchone():
            clean_name = f"{base} ({suffix})"
            suffix += 1
        if is_default:
            con.execute("UPDATE profile SET is_default=0 WHERE user_id=?", (user_id,))
        cur = con.execute(
            f"INSERT INTO profile (user_id, name, is_default, {', '.join(values.keys())}, created_at, updated_at) "
            f"VALUES (?, ?, ?, {', '.join(['?'] * len(values))}, ?, ?)",
            [user_id, clean_name, is_default, *values.values(), now, now],
        )
        return int(cur.lastrowid)


def update_profile_fields(user_id: int, profile_id: int, profile: Dict[str, Any]) -> bool:
    now = utc_now()
    values = {k: profile.get(k, "") for k in PROFILE_FIELDS}
    with connect() as con:
        if not con.execute("SELECT 1 FROM profile WHERE id=? AND user_id=?", (profile_id, user_id)).fetchone():
            return False
        if profile.get("name"):
            new_name = profile["name"].strip()
            if new_name and not con.execute(
                "SELECT 1 FROM profile WHERE user_id=? AND name=? AND id<>?", (user_id, new_name, profile_id)
            ).fetchone():
                con.execute("UPDATE profile SET name=? WHERE id=? AND user_id=?", (new_name, profile_id, user_id))
        assignments = ", ".join(f"{k}=?" for k in values.keys())
        con.execute(
            f"UPDATE profile SET {assignments}, updated_at=? WHERE id=? AND user_id=?",
            [*values.values(), now, profile_id, user_id],
        )
        return True


def set_default_profile(user_id: int, profile_id: int) -> bool:
    with connect() as con:
        if not con.execute("SELECT 1 FROM profile WHERE id=? AND user_id=?", (profile_id, user_id)).fetchone():
            return False
        con.execute("UPDATE profile SET is_default=0 WHERE user_id=?", (user_id,))
        con.execute("UPDATE profile SET is_default=1 WHERE id=? AND user_id=?", (profile_id, user_id))
        return True


def delete_profile(user_id: int, profile_id: int) -> bool:
    with connect() as con:
        count = con.execute("SELECT COUNT(*) AS c FROM profile WHERE user_id=?", (user_id,)).fetchone()["c"]
        if count <= 1:
            raise ValueError("Cannot delete your only profile.")
        row = con.execute("SELECT is_default FROM profile WHERE id=? AND user_id=?", (profile_id, user_id)).fetchone()
        if not row:
            return False
        con.execute("DELETE FROM profile WHERE id=? AND user_id=?", (profile_id, user_id))
        if row["is_default"]:
            # Promote the most recent remaining profile to default.
            con.execute(
                "UPDATE profile SET is_default=1 WHERE id=(SELECT id FROM profile WHERE user_id=? ORDER BY id DESC LIMIT 1)",
                (user_id,),
            )
        return True


def list_profiles(user_id: int) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM profile WHERE user_id=? ORDER BY is_default DESC, name ASC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_profile(user_id: int = 1, profile_id: int | None = None) -> Dict[str, Any]:
    with connect() as con:
        if profile_id is not None:
            row = con.execute("SELECT * FROM profile WHERE id=? AND user_id=?", (profile_id, user_id)).fetchone()
            return dict(row) if row else {}
        row = con.execute(
            "SELECT * FROM profile WHERE user_id=? ORDER BY is_default DESC, id ASC LIMIT 1", (user_id,)
        ).fetchone()
        return dict(row) if row else {}


def insert_job(job: Dict[str, Any], user_id: int = 1, workspace_id: int | None = None) -> int:
    now = utc_now()
    opportunity_type = str(job.get("opportunity_type") or "job").lower()
    if opportunity_type not in OPPORTUNITY_TYPES:
        opportunity_type = "other"
    classification = str(job.get("classification") or opportunity_type).lower()
    if classification not in OPPORTUNITY_TYPES:
        classification = "unknown"
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
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
            "created_at": now,
            "updated_at": now,
        }
        cols = list(payload.keys())
        try:
            cur = con.execute(
                f"INSERT INTO jobs ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
                [payload[c] for c in cols],
            )
            job_id = int(cur.lastrowid)
            con.execute("INSERT OR IGNORE INTO applications(job_id, status, notes, last_updated) VALUES (?, 'New', '', ?)", (job_id, now))
            add_audit_log(user_id, "opportunity.create", "job", str(job_id), {"title": payload["title"]}, con=con, workspace_id=scoped_workspace_id, organization_id=organization_id)
            return job_id
        except sqlite3.IntegrityError:
            row = con.execute("SELECT id FROM jobs WHERE user_id = ? AND workspace_id=? AND url = ?", (user_id, scoped_workspace_id, payload["url"])).fetchone()
            if row:
                return int(row["id"])
            raise


def job_url_exists(url: str, user_id: int = 1, workspace_id: int | None = None) -> bool:
    if not (url or "").strip():
        return False
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        row = con.execute(
            "SELECT 1 FROM jobs WHERE user_id = ? AND workspace_id = ? AND url = ? LIMIT 1",
            (user_id, scoped_workspace_id, url.strip()),
        ).fetchone()
        return bool(row)


def list_jobs(user_id: int = 1, workspace_id: int | None = None, content_type: str = "job") -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        filters = ["j.user_id = ?", "j.workspace_id = ?"]
        params: list[Any] = [user_id, scoped_workspace_id]
        normalized_content_type = (content_type or "job").strip().lower()
        if normalized_content_type in {"job", "jobs"}:
            placeholders = ",".join(["?"] * len(JOB_LIKE_TYPES))
            filters.append(
                f"(lower(COALESCE(j.classification, j.opportunity_type, '')) IN ({placeholders}) "
                f"OR lower(COALESCE(j.opportunity_type, '')) IN ({placeholders}))"
            )
            params.extend(JOB_LIKE_TYPES)
            params.extend(JOB_LIKE_TYPES)
        elif normalized_content_type not in {"all", "any"}:
            filters.append("(lower(COALESCE(j.classification, j.opportunity_type, '')) = ? OR lower(COALESCE(j.opportunity_type, '')) = ?)")
            params.extend([normalized_content_type, normalized_content_type])
        rows = con.execute(
            f"""
            SELECT j.*, a.status, a.notes, e.match_score, e.priority,
                   m.cover_letter, m.screening_answers
            FROM jobs j
            LEFT JOIN applications a ON a.job_id = j.id
            LEFT JOIN evaluations e ON e.job_id = j.id
            LEFT JOIN application_materials m ON m.job_id = j.id
            WHERE {' AND '.join(filters)}
            ORDER BY COALESCE(e.match_score, -1) DESC, j.updated_at DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_job(job_id: int, user_id: int = 1, workspace_id: int | None = None) -> dict[str, Any]:
    with connect() as con:
        if workspace_id is None:
            row = con.execute(
                """
                SELECT j.*, a.status, a.notes, e.match_score, e.priority,
                       e.good_fit, e.weak_areas, e.red_flags
                FROM jobs j
                LEFT JOIN applications a ON a.job_id = j.id
                LEFT JOIN evaluations e ON e.job_id = j.id
                WHERE j.id=? AND j.user_id=?
                """,
                (job_id, user_id),
            ).fetchone()
        else:
            scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
            row = con.execute(
                """
                SELECT j.*, a.status, a.notes, e.match_score, e.priority,
                       e.good_fit, e.weak_areas, e.red_flags
                FROM jobs j
                LEFT JOIN applications a ON a.job_id = j.id
                LEFT JOIN evaluations e ON e.job_id = j.id
                WHERE j.id=? AND j.user_id=? AND j.workspace_id=?
                """,
                (job_id, user_id, scoped_workspace_id),
            ).fetchone()
        if not row:
            return {}
        item = dict(row)
        evaluation = get_evaluation(job_id, user_id)
        item["evaluation"] = evaluation or None
        return item


def delete_job(job_id: int, user_id: int = 1, workspace_id: int | None = None) -> None:
    with connect() as con:
        if workspace_id is None:
            row = con.execute("SELECT workspace_id, organization_id FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
            if not row:
                return
        else:
            scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
            row = con.execute("SELECT workspace_id, organization_id FROM jobs WHERE id=? AND user_id=? AND workspace_id=?", (job_id, user_id, scoped_workspace_id)).fetchone()
            if not row:
                return
        for table in [
            "evaluations",
            "application_materials",
            "applications",
            "reminders",
            "resume_reviews",
            "interview_prep_sessions",
            "recordings",
        ]:
            con.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))
        con.execute("DELETE FROM jobs WHERE id=? AND user_id=?", (job_id, user_id))
        if row:
            add_audit_log(user_id, "opportunity.delete", "job", str(job_id), {}, con=con, workspace_id=row["workspace_id"], organization_id=row["organization_id"])


JOB_DATA_TABLE_ORDER = [
    "evaluations",
    "application_materials",
    "applications",
    "reminders",
    "resume_reviews",
    "interview_prep_sessions",
    "recordings",
    "jobs",
]


def _table_exists(con, table_name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def clear_job_data(user_id: int | None = None, *, dry_run: bool = True) -> dict[str, Any]:
    """Clear generated opportunity/job data while preserving accounts and settings."""
    with connect() as con:
        job_filter_sql = "SELECT id FROM jobs"
        params: list[Any] = []
        if user_id is not None:
            job_filter_sql += " WHERE user_id=?"
            params.append(int(user_id))

        job_ids = [int(row["id"]) for row in con.execute(job_filter_sql, params).fetchall()] if _table_exists(con, "jobs") else []
        job_id_params: list[Any] = job_ids
        placeholders = ",".join(["?"] * len(job_ids))
        counts: dict[str, int] = {}

        def count_rows(table: str, where_sql: str = "", where_params: list[Any] | None = None) -> int:
            if not _table_exists(con, table):
                return 0
            sql = f"SELECT COUNT(*) AS count FROM {table}"
            if where_sql:
                sql += f" WHERE {where_sql}"
            return int(con.execute(sql, where_params or []).fetchone()["count"] or 0)

        counts["evaluations"] = count_rows("evaluations", f"job_id IN ({placeholders})", job_id_params) if job_ids else 0
        counts["application_materials"] = count_rows("application_materials", f"job_id IN ({placeholders})", job_id_params) if job_ids else 0
        counts["applications"] = count_rows("applications", f"job_id IN ({placeholders})", job_id_params) if job_ids else 0
        counts["reminders"] = count_rows("reminders", f"job_id IN ({placeholders})", job_id_params) if job_ids else 0
        if user_id is None:
            counts["resume_reviews"] = count_rows("resume_reviews")
            counts["interview_prep_sessions"] = count_rows("interview_prep_sessions")
            counts["recordings"] = count_rows("recordings")
            counts["jobs"] = count_rows("jobs")
        else:
            counts["resume_reviews"] = count_rows("resume_reviews", "user_id=?", [int(user_id)])
            counts["interview_prep_sessions"] = count_rows("interview_prep_sessions", "user_id=?", [int(user_id)])
            counts["recordings"] = count_rows("recordings", "user_id=?", [int(user_id)])
            counts["jobs"] = count_rows("jobs", "user_id=?", [int(user_id)])

        result = {
            "dry_run": dry_run,
            "user_id": user_id,
            "tables": counts,
            "total_rows": sum(counts.values()),
            "preserved": [
                "users",
                "profile",
                "user_sessions",
                "password_reset_tokens",
                "integration_settings",
                "provider_configs",
                "automation_preferences",
                "organizations",
                "workspaces",
                "workspace_members",
            ],
        }
        if dry_run:
            return result

        if job_ids:
            con.execute(f"DELETE FROM evaluations WHERE job_id IN ({placeholders})", job_id_params)
            con.execute(f"DELETE FROM application_materials WHERE job_id IN ({placeholders})", job_id_params)
            con.execute(f"DELETE FROM applications WHERE job_id IN ({placeholders})", job_id_params)
            con.execute(f"DELETE FROM reminders WHERE job_id IN ({placeholders})", job_id_params)
        if user_id is None:
            con.execute("DELETE FROM resume_reviews")
            con.execute("DELETE FROM interview_prep_sessions")
            con.execute("DELETE FROM recordings")
            con.execute("DELETE FROM jobs")
        else:
            con.execute("DELETE FROM resume_reviews WHERE user_id=?", (int(user_id),))
            con.execute("DELETE FROM interview_prep_sessions WHERE user_id=?", (int(user_id),))
            con.execute("DELETE FROM recordings WHERE user_id=?", (int(user_id),))
            con.execute("DELETE FROM jobs WHERE user_id=?", (int(user_id),))
        result["deleted"] = counts
        return result


def save_integration_settings(
    user_id: int,
    service: str,
    api_key: str = "",
    config: Dict[str, Any] | None = None,
    *,
    keep_existing_api_key_if_blank: bool = False,
    workspace_id: int | None = None,
) -> None:
    """Save per-user, per-workspace integration settings with encrypted secrets."""
    encrypted_config = encrypt_text(json.dumps(config or {}))
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
        existing = con.execute(
            "SELECT api_key FROM integration_settings WHERE user_id=? AND workspace_id=? AND service=?",
            (user_id, scoped_workspace_id, service),
        ).fetchone()
        if keep_existing_api_key_if_blank and not (api_key or "").strip() and existing:
            encrypted_key = existing["api_key"] or ""
        else:
            encrypted_key = encrypt_text(api_key or "")

        con.execute(
            """
            INSERT INTO integration_settings(user_id, workspace_id, organization_id, service, api_key, config_json, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(user_id, workspace_id, service) DO UPDATE SET
                organization_id=excluded.organization_id,
                api_key=excluded.api_key,
                config_json=excluded.config_json,
                updated_at=excluded.updated_at
            """,
            (user_id, scoped_workspace_id, organization_id, service, encrypted_key, encrypted_config, utc_now()),
        )
        add_audit_log(user_id, "integration.upsert", "integration", service, {"has_api_key": bool((api_key or "").strip())}, con=con, workspace_id=scoped_workspace_id, organization_id=organization_id)


def get_integration_settings(user_id: int, service: str, workspace_id: int | None = None) -> dict[str, Any]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        row = con.execute(
            "SELECT * FROM integration_settings WHERE user_id=? AND workspace_id=? AND service=?",
            (user_id, scoped_workspace_id, service),
        ).fetchone()
    if not row:
        return {}
    settings = dict(row)
    settings["api_key"] = decrypt_text(settings.get("api_key") or "")
    try:
        settings["config"] = json.loads(decrypt_text(settings.get("config_json") or "{}") or "{}")
    except json.JSONDecodeError:
        settings["config"] = {}
    return settings


def delete_integration_settings(user_id: int, service: str, workspace_id: int | None = None) -> None:
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
        con.execute("DELETE FROM integration_settings WHERE user_id=? AND workspace_id=? AND service=?", (user_id, scoped_workspace_id, service))
        add_audit_log(user_id, "integration.delete", "integration", service, {}, con=con, workspace_id=scoped_workspace_id, organization_id=organization_id)


def has_integration_api_key(user_id: int, service: str, workspace_id: int | None = None) -> bool:
    settings = get_integration_settings(user_id, service, workspace_id=workspace_id)
    return bool((settings.get("api_key") or "").strip())


def list_integration_settings(user_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
    """List the current user's workspace-scoped integrations without decrypted secrets."""
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        rows = con.execute(
            "SELECT service, api_key, config_json, updated_at, workspace_id, organization_id FROM integration_settings WHERE user_id=? AND workspace_id=? ORDER BY service",
            (user_id, scoped_workspace_id),
        ).fetchall()
    integrations: list[dict[str, Any]] = []
    for row in rows:
        config: dict[str, Any] = {}
        try:
            config = json.loads(decrypt_text(row["config_json"] or "{}") or "{}")
        except json.JSONDecodeError:
            config = {}
        integrations.append(
            {
                "service": row["service"],
                "workspace_id": row["workspace_id"],
                "organization_id": row["organization_id"],
                "has_api_key": bool(decrypt_text(row["api_key"] or "").strip()),
                "config": config,
                "updated_at": row["updated_at"],
            }
        )
    return integrations


def _safe_json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def save_provider_config(
    user_id: int,
    platform: str,
    provider_name: str,
    *,
    auth_type: str = "api_key",
    credentials: Dict[str, Any] | None = None,
    config: Dict[str, Any] | None = None,
    priority: int = 100,
    is_active: bool = True,
    keep_existing_credentials_if_blank: bool = False,
    workspace_id: int | None = None,
) -> None:
    """Save a workspace-owned provider configuration with encrypted credentials."""
    platform = (platform or "").strip().lower()
    provider_name = (provider_name or "").strip().lower()
    if not platform or not provider_name:
        raise ValueError("platform and provider_name are required")

    clean_credentials = {k: v for k, v in (credentials or {}).items() if str(v or "").strip()}
    encrypted_config = encrypt_text(json.dumps(config or {}))
    now = utc_now()
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
        existing = con.execute(
            "SELECT encrypted_credentials FROM provider_configs WHERE user_id=? AND workspace_id=? AND platform=? AND provider_name=?",
            (user_id, scoped_workspace_id, platform, provider_name),
        ).fetchone()
        if keep_existing_credentials_if_blank and not clean_credentials and existing:
            encrypted_credentials = existing["encrypted_credentials"] or ""
        else:
            encrypted_credentials = encrypt_text(json.dumps(clean_credentials))
        con.execute(
            """
            INSERT INTO provider_configs(
                user_id, workspace_id, organization_id, platform, provider_name, auth_type, encrypted_credentials, config_json,
                priority, is_active, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, workspace_id, platform, provider_name) DO UPDATE SET
                organization_id=excluded.organization_id,
                auth_type=excluded.auth_type,
                encrypted_credentials=excluded.encrypted_credentials,
                config_json=excluded.config_json,
                priority=excluded.priority,
                is_active=excluded.is_active,
                updated_at=excluded.updated_at
            """,
            (user_id, scoped_workspace_id, organization_id, platform, provider_name, auth_type, encrypted_credentials, encrypted_config, int(priority), 1 if is_active else 0, now, now),
        )
        add_audit_log(
            user_id,
            "provider_config.upsert",
            "provider_config",
            f"{platform}:{provider_name}",
            {"platform": platform, "provider_name": provider_name, "auth_type": auth_type, "has_credentials": bool(clean_credentials)},
            con=con, workspace_id=scoped_workspace_id, organization_id=organization_id,
        )


def _provider_row_to_dict(row, *, include_credentials: bool = False) -> dict[str, Any]:
    item = dict(row)
    config = _safe_json_loads(decrypt_text(item.get("config_json") or "{}"), {})
    credentials = _safe_json_loads(decrypt_text(item.get("encrypted_credentials") or "{}"), {})
    item["config"] = config
    item["has_credentials"] = bool(credentials)
    item["is_active"] = bool(item.get("is_active"))
    item.pop("encrypted_credentials", None)
    item.pop("config_json", None)
    if include_credentials:
        item["credentials"] = credentials
    return item


def get_provider_config(user_id: int, platform: str, provider_name: str, *, include_credentials: bool = False, workspace_id: int | None = None) -> dict[str, Any]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        row = con.execute(
            "SELECT * FROM provider_configs WHERE user_id=? AND workspace_id=? AND platform=? AND provider_name=?",
            (user_id, scoped_workspace_id, platform.lower(), provider_name.lower()),
        ).fetchone()
    return _provider_row_to_dict(row, include_credentials=include_credentials) if row else {}


def list_provider_configs(user_id: int, platform: str | None = None, *, include_credentials: bool = False, workspace_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        if platform:
            rows = con.execute(
                "SELECT * FROM provider_configs WHERE user_id=? AND workspace_id=? AND platform=? ORDER BY priority ASC, provider_name ASC",
                (user_id, scoped_workspace_id, platform.lower()),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM provider_configs WHERE user_id=? AND workspace_id=? ORDER BY platform ASC, priority ASC, provider_name ASC",
                (user_id, scoped_workspace_id),
            ).fetchall()
    return [_provider_row_to_dict(row, include_credentials=include_credentials) for row in rows]


def delete_provider_config(user_id: int, platform: str, provider_name: str, workspace_id: int | None = None) -> None:
    platform = platform.lower()
    provider_name = provider_name.lower()
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
        con.execute(
            "DELETE FROM provider_configs WHERE user_id=? AND workspace_id=? AND platform=? AND provider_name=?",
            (user_id, scoped_workspace_id, platform, provider_name),
        )
        add_audit_log(user_id, "provider_config.delete", "provider_config", f"{platform}:{provider_name}", {}, con=con, workspace_id=scoped_workspace_id, organization_id=organization_id)


def record_provider_health(
    user_id: int,
    platform: str,
    provider_name: str,
    health_status: str,
    *,
    latency_ms: int | None = None,
    error_message: str = "",
    workspace_id: int | None = None,
) -> None:
    now = utc_now()
    platform = platform.lower()
    provider_name = provider_name.lower()
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        row = con.execute(
            "SELECT success_count, failure_count FROM provider_configs WHERE user_id=? AND workspace_id=? AND platform=? AND provider_name=?",
            (user_id, scoped_workspace_id, platform, provider_name),
        ).fetchone()
        if not row:
            return
        success_count = int(row["success_count"] or 0)
        failure_count = int(row["failure_count"] or 0)
        last_success_at = None
        last_failure_at = None
        if health_status == "healthy":
            success_count += 1
            last_success_at = now
        elif health_status in {"failed", "missing_credentials", "unhealthy"}:
            failure_count += 1
            last_failure_at = now
        con.execute(
            """
            UPDATE provider_configs
            SET health_status=?, last_health_check_at=?,
                last_success_at=COALESCE(?, last_success_at),
                last_failure_at=COALESCE(?, last_failure_at),
                success_count=?, failure_count=?, latency_ms=?, last_error=?, updated_at=?
            WHERE user_id=? AND workspace_id=? AND platform=? AND provider_name=?
            """,
            (
                health_status,
                now,
                last_success_at,
                last_failure_at,
                success_count,
                failure_count,
                latency_ms,
                error_message,
                now,
                user_id,
                scoped_workspace_id,
                platform,
                provider_name,
            ),
        )


def save_evaluation(job_id: int, evaluation: Dict[str, Any], user_id: int = 1) -> None:
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
        if not con.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
            raise ValueError("Job not found for user")
        con.execute(
            f"INSERT OR REPLACE INTO evaluations ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
            [values[c] for c in cols],
        )


def get_evaluation(job_id: int, user_id: int = 1) -> dict[str, Any]:
    with connect() as con:
        row = con.execute(
            """
            SELECT e.* FROM evaluations e
            JOIN jobs j ON j.id = e.job_id
            WHERE e.job_id=? AND j.user_id=?
            """,
            (job_id, user_id),
        ).fetchone()
        return dict(row) if row else {}


def cleanup_non_opportunity_records(user_id: int = 1, workspace_id: int | None = None) -> dict[str, Any]:
    from job_assistant.services.opportunity_classifier import annotate_opportunity

    updated = 0
    evaluations_removed = 0
    inspected = 0
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        rows = con.execute(
            """
            SELECT j.*
            FROM jobs j
            WHERE j.user_id=? AND j.workspace_id=?
              AND (
                lower(COALESCE(j.source, '')) LIKE '%gmail%'
                OR lower(COALESCE(j.title, '')) LIKE 'subject:%'
                OR lower(COALESCE(j.company, '')) IN ('unknown company', 'unknown')
                OR lower(COALESCE(j.description, '') || ' ' || COALESCE(j.raw_text, '')) LIKE '%newsletter%'
                OR lower(COALESCE(j.url, '')) LIKE '%medium.com%'
                OR lower(COALESCE(j.url, '')) LIKE '%sendgrid%'
              )
            """
            ,
            (user_id, scoped_workspace_id),
        ).fetchall()
        for row in rows:
            inspected += 1
            item = dict(row)
            annotated = annotate_opportunity(item)
            if annotated.get("importable"):
                continue
            now = utc_now()
            con.execute(
                """
                UPDATE jobs
                SET classification=?, classification_reason=?, classification_confidence=?,
                    opportunity_confidence=?, importable=0, blocked_reason=?, updated_at=?
                WHERE id=? AND user_id=?
                """,
                (
                    annotated.get("classification") or "unknown",
                    annotated.get("classification_reason") or "",
                    annotated.get("classification_confidence") or 0,
                    annotated.get("opportunity_confidence") or 0,
                    annotated.get("blocked_reason") or "Non-opportunity content rejected by classifier.",
                    now,
                    row["id"],
                    user_id,
                ),
            )
            con.execute(
                """
                INSERT INTO applications(job_id, status, notes, last_updated)
                VALUES (?, 'Non-Opportunity', ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET status='Non-Opportunity', notes=excluded.notes, last_updated=excluded.last_updated
                """,
                (row["id"], annotated.get("blocked_reason") or annotated.get("classification_reason") or "", now),
            )
            cur = con.execute("DELETE FROM evaluations WHERE job_id=?", (row["id"],))
            evaluations_removed += cur.rowcount or 0
            updated += 1
    return {"inspected": inspected, "updated": updated, "evaluations_removed": evaluations_removed}


def save_materials(job_id: int, materials: Dict[str, Any], user_id: int = 1) -> None:
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
        if not con.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
            raise ValueError("Job not found for user")
        con.execute(
            f"INSERT OR REPLACE INTO application_materials ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
            [values[c] for c in cols],
        )


def get_materials(job_id: int, user_id: int = 1) -> dict[str, Any]:
    with connect() as con:
        row = con.execute(
            """
            SELECT m.* FROM application_materials m
            JOIN jobs j ON j.id = m.job_id
            WHERE m.job_id=? AND j.user_id=?
            """,
            (job_id, user_id),
        ).fetchone()
        return dict(row) if row else {}


def update_status(job_id: int, status: str, notes: str = "", user_id: int = 1) -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    with connect() as con:
        if not con.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
            raise ValueError("Job not found for user")
        con.execute(
            "INSERT INTO applications(job_id,status,notes,last_updated) VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, notes=excluded.notes, last_updated=excluded.last_updated",
            (job_id, status, notes, utc_now()),
        )


def save_resume_review(user_id: int, review: Dict[str, Any], job_id: int | None = None) -> dict[str, Any]:
    now = utc_now()
    with connect() as con:
        if job_id and not con.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
            raise ValueError("Job not found for user")
        cur = con.execute(
            "INSERT INTO resume_reviews(user_id, job_id, review_json, created_at) VALUES (?,?,?,?)",
            (user_id, job_id, json.dumps(review), now),
        )
        review["id"] = int(cur.lastrowid)
        review["job_id"] = job_id
        review["created_at"] = now
        return review


def list_resume_reviews(user_id: int, job_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as con:
        if job_id:
            rows = con.execute(
                "SELECT * FROM resume_reviews WHERE user_id=? AND job_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, job_id, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM resume_reviews WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
    output = []
    for row in rows:
        item = json.loads(row["review_json"] or "{}")
        item.update({"id": row["id"], "job_id": row["job_id"], "created_at": row["created_at"]})
        output.append(item)
    return output


def save_interview_prep(user_id: int, job_id: int, prep: Dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    with connect() as con:
        if not con.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
            raise ValueError("Job not found for user")
        cur = con.execute(
            "INSERT INTO interview_prep_sessions(user_id, job_id, prep_json, created_at) VALUES (?,?,?,?)",
            (user_id, job_id, json.dumps(prep), now),
        )
        prep["id"] = int(cur.lastrowid)
        prep["job_id"] = job_id
        prep["created_at"] = now
        return prep


def list_interview_prep(user_id: int, job_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as con:
        if job_id:
            rows = con.execute(
                "SELECT * FROM interview_prep_sessions WHERE user_id=? AND job_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, job_id, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM interview_prep_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
    output = []
    for row in rows:
        item = json.loads(row["prep_json"] or "{}")
        item.update({"id": row["id"], "job_id": row["job_id"], "created_at": row["created_at"]})
        output.append(item)
    return output


def save_recording(user_id: int, recording: Dict[str, Any], job_id: int | None = None) -> dict[str, Any]:
    now = utc_now()
    with connect() as con:
        if job_id and not con.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
            raise ValueError("Job not found for user")
        cur = con.execute(
            """
            INSERT INTO recordings(
                user_id, job_id, title, mime_type, data_url, duration_ms, created_at,
                interview_prep_session_id, original_filename, stored_path, playback_url, file_size, storage_type
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                job_id,
                recording.get("title", "Interview practice recording"),
                recording.get("mime_type", "audio/webm"),
                recording.get("data_url", ""),
                int(recording.get("duration_ms") or 0),
                now,
                recording.get("interview_prep_session_id"),
                recording.get("original_filename", ""),
                recording.get("stored_path", ""),
                recording.get("playback_url", ""),
                int(recording.get("file_size") or 0),
                recording.get("storage_type", ""),
            ),
        )
        return {"id": int(cur.lastrowid), "job_id": job_id, "created_at": now, **recording}


def list_recordings(user_id: int, job_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as con:
        if job_id:
            rows = con.execute("SELECT * FROM recordings WHERE user_id=? AND job_id=? ORDER BY created_at DESC LIMIT ?", (user_id, job_id, limit)).fetchall()
        else:
            rows = con.execute("SELECT * FROM recordings WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        if not item.get("playback_url") and item.get("data_url"):
            item["playback_url"] = item["data_url"]
        output.append(item)
    return output


def save_gmail_messages(user_id: int, messages: list[Dict[str, Any]]) -> list[dict[str, Any]]:
    from job_assistant.services.opportunity_classifier import annotate_opportunity, extract_opportunities_from_container

    saved: list[dict[str, Any]] = []
    now = utc_now()
    with connect() as con:
        for message in messages:
            message = dict(message)
            message_id = str(message.get("message_id") or message.get("id") or "")
            thread_id = str(message.get("thread_id") or message.get("threadId") or "")
            open_url = message.get("open_url") or (f"https://mail.google.com/mail/u/0/#inbox/{thread_id or message_id}" if (thread_id or message_id) else "")
            classification = annotate_opportunity(
                {
                    "title": message.get("subject", ""),
                    "subject": message.get("subject", ""),
                    "sender": message.get("sender") or message.get("from") or "",
                    "snippet": message.get("snippet", ""),
                    "body": message.get("body", ""),
                    "source": "Gmail",
                    "source_type": "gmail",
                    "message_id": message_id,
                    "open_url": open_url,
                }
            )
            extracted = extract_opportunities_from_container({**classification, **message, "open_url": open_url, "source": "Gmail", "source_type": "gmail"})
            message.update(
                {
                    "classification": classification.get("classification"),
                    "classification_confidence": classification.get("classification_confidence"),
                    "classification_reason": classification.get("classification_reason"),
                    "opportunity_confidence": classification.get("opportunity_confidence"),
                    "importable": classification.get("importable"),
                    "blocked_reason": classification.get("blocked_reason"),
                    "extracted_opportunities_count": len(extracted),
                    "extracted_opportunities": extracted,
                }
            )
            cur = con.execute(
                """
                INSERT INTO gmail_messages(user_id, message_id, thread_id, sender, subject, date, snippet, open_url, payload_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    user_id,
                    message_id,
                    thread_id,
                    message.get("sender") or message.get("from") or "",
                    message.get("subject", ""),
                    message.get("date", ""),
                    message.get("snippet", ""),
                    open_url,
                    json.dumps(message),
                    now,
                ),
            )
            saved.append({"id": int(cur.lastrowid), **message, "open_url": open_url, "created_at": now})
    return saved


def list_gmail_messages(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute("SELECT * FROM gmail_messages WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
    return [dict(row) for row in rows]


def create_reminder(job_id: int, kind: str, remind_at: str, note: str, user_id: int = 1) -> None:
    with connect() as con:
        if not con.execute("SELECT 1 FROM jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone():
            raise ValueError("Job not found for user")
        con.execute(
            "INSERT INTO reminders(job_id, kind, remind_at, note, created_at) VALUES (?,?,?,?,?)",
            (job_id, kind, remind_at, note, utc_now()),
        )


def create_followup_reminders(after_days: int = 7) -> int:
    """Create follow-up reminders for applications stuck in 'Applied' with no
    status change in ``after_days`` days. Idempotent: skips jobs that already
    have an open auto follow-up reminder. Runs across all users (system job).
    Returns the number of reminders created.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, after_days))).isoformat(timespec="seconds")
    now = utc_now()
    with connect() as con:
        rows = con.execute(
            """
            SELECT a.job_id, j.company FROM applications a
            JOIN jobs j ON j.id = a.job_id
            WHERE a.status = 'Applied' AND a.last_updated <= ?
              AND NOT EXISTS (
                SELECT 1 FROM reminders r
                WHERE r.job_id = a.job_id AND r.kind = 'followup' AND r.done = 0
              )
            """,
            (cutoff,),
        ).fetchall()
        created = 0
        for row in rows:
            company = (row["company"] or "this company").strip() or "this company"
            note = f"No response from {company} in {after_days} days — consider following up."
            con.execute(
                "INSERT INTO reminders(job_id, kind, remind_at, note, created_at) VALUES (?,?,?,?,?)",
                (row["job_id"], "followup", now, note, now),
            )
            created += 1
    return created


def due_reminders(user_id: int = 1) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute(
            """
            SELECT r.*, j.title, j.company FROM reminders r
            LEFT JOIN jobs j ON j.id = r.job_id
            WHERE j.user_id = ? AND r.done = 0 AND r.remind_at <= ?
            ORDER BY r.remind_at ASC
            """,
            (user_id, utc_now()),
        ).fetchall()
        return [dict(r) for r in rows]



def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session_token(user_id: int, days: int = 30) -> str:
    token = secrets.token_urlsafe(48)
    now = utc_now()
    from datetime import datetime, timezone, timedelta
    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
    with connect() as con:
        con.execute(
            "INSERT INTO user_sessions(user_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
            (user_id, _token_hash(token), now, expires_at),
        )
    return token


def get_user_by_session_token(token: str) -> dict[str, Any]:
    if not token:
        return {}
    with connect() as con:
        row = con.execute(
            """
            SELECT u.* FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash=?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
              AND u.is_active=1
            """,
            (_token_hash(token), utc_now()),
        ).fetchone()
        return dict(row) if row else {}


def revoke_session_token(token: str) -> None:
    if not token:
        return
    with connect() as con:
        con.execute("UPDATE user_sessions SET revoked_at=? WHERE token_hash=?", (utc_now(), _token_hash(token)))


def _ensure_password_reset_table(con) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            ip_address TEXT,
            user_agent TEXT
        )
        """
    )


def create_password_reset_token(user_id: int, token: str, expires_at: str, ip_address: str = "", user_agent: str = "") -> int:
    now = utc_now()
    with connect() as con:
        _ensure_password_reset_table(con)
        cur = con.execute(
            """
            INSERT INTO password_reset_tokens(user_id, token_hash, created_at, expires_at, ip_address, user_agent)
            VALUES (?,?,?,?,?,?)
            """,
            (user_id, _token_hash(token), now, expires_at, ip_address, user_agent),
        )
        return int(cur.lastrowid)


def get_password_reset_token(token: str) -> dict[str, Any]:
    if not token:
        return {}
    now = utc_now()
    token_hash = _token_hash(token)
    with connect() as con:
        _ensure_password_reset_table(con)
        row = con.execute(
            """
            SELECT prt.*, u.email FROM password_reset_tokens prt
            JOIN users u ON u.id = prt.user_id
            WHERE prt.token_hash=?
              AND prt.consumed_at IS NULL
              AND prt.expires_at > ?
              AND u.is_active=1
            """,
            (token_hash, now),
        ).fetchone()
        return dict(row) if row else {}


def consume_password_reset_token(token_id: int) -> bool:
    with connect() as con:
        cur = con.execute(
            "UPDATE password_reset_tokens SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
            (utc_now(), token_id),
        )
        return cur.rowcount == 1


def update_user_password(user_id: int, password_hash: str) -> None:
    with connect() as con:
        con.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (password_hash, utc_now(), user_id))


def revoke_user_sessions(user_id: int) -> None:
    with connect() as con:
        con.execute("UPDATE user_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (utc_now(), user_id))


def get_automation_preferences(user_id: int) -> dict[str, Any]:
    with connect() as con:
        row = con.execute("SELECT * FROM automation_preferences WHERE user_id=?", (user_id,)).fetchone()
    if row:
        data = dict(row)
    else:
        data = {
            "user_id": user_id,
            "enabled": 0,
            "gmail_enabled": 1,
            "public_sources_enabled": 1,
            "linkedin_api_enabled": 0,
            "score_new": 1,
            "generate_materials": 0,
            "gmail_interval_minutes": 30,
            "public_interval_hours": 6,
            "linkedin_interval_hours": 6,
            "daily_summary_hour": 8,
            "notify_in_app": 1,
            "min_score_for_materials": 70,
            "updated_at": utc_now(),
        }
    for key in ["enabled", "gmail_enabled", "public_sources_enabled", "linkedin_api_enabled", "score_new", "generate_materials", "notify_in_app"]:
        data[key] = bool(data.get(key))
    return data


def save_automation_preferences(user_id: int, prefs: Dict[str, Any]) -> None:
    current = get_automation_preferences(user_id)
    current.update(prefs or {})
    fields = [
        "enabled", "gmail_enabled", "public_sources_enabled", "linkedin_api_enabled", "score_new", "generate_materials",
        "gmail_interval_minutes", "public_interval_hours", "linkedin_interval_hours", "daily_summary_hour", "notify_in_app",
        "min_score_for_materials",
    ]
    values = {k: int(current[k]) if isinstance(current[k], bool) else current[k] for k in fields}
    values["updated_at"] = utc_now()
    with connect() as con:
        con.execute(
            f"""
            INSERT INTO automation_preferences(user_id, {', '.join(values.keys())})
            VALUES (?, {', '.join(['?'] * len(values))})
            ON CONFLICT(user_id) DO UPDATE SET {', '.join([f'{k}=excluded.{k}' for k in values.keys()])}
            """,
            [user_id, *values.values()],
        )


def add_activity_event(user_id: int, title: str, message: str = "", level: str = "info", metadata: Dict[str, Any] | None = None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO activity_events(user_id, level, title, message, metadata_json, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, level, title, message, json.dumps(metadata or {}), utc_now()),
        )


def list_activity_events(user_id: int, limit: int = 50, unread_only: bool = False) -> list[dict[str, Any]]:
    where = "WHERE user_id=?" + (" AND read_at IS NULL" if unread_only else "")
    with connect() as con:
        rows = con.execute(
            f"SELECT * FROM activity_events {where} ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_activity_read(user_id: int) -> None:
    with connect() as con:
        con.execute("UPDATE activity_events SET read_at=? WHERE user_id=? AND read_at IS NULL", (utc_now(), user_id))



FEEDBACK_CATEGORIES = [
    "Bug Report",
    "Feature Request",
    "AI Quality Issue",
    "UI/UX Feedback",
    "Provider/API Problem",
    "Performance Issue",
    "Security Concern",
    "Automation Failure",
    "Integration Request",
    "General Suggestion",
]
FEEDBACK_SEVERITIES = ["low", "medium", "high", "critical"]
FEEDBACK_STATUSES = ["open", "triaged", "in_review", "planned", "in_progress", "resolved", "closed", "duplicate", "wont_fix"]


def create_feedback(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    """Create workspace-scoped user feedback with safe metadata only."""
    category = str(payload.get("category") or "General Suggestion").strip()
    if category not in FEEDBACK_CATEGORIES:
        category = "General Suggestion"
    severity = str(payload.get("severity") or "medium").strip().lower()
    if severity not in FEEDBACK_SEVERITIES:
        severity = "medium"
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    if not title or not description:
        raise ValueError("Feedback title and description are required")
    now = utc_now()
    metadata = payload.get("metadata") or {}
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id or payload.get("workspace_id"))
        cur = con.execute(
            """
            INSERT INTO feedback(
                user_id, workspace_id, organization_id, category, title, description, severity, status, attachment_url,
                page_url, user_agent, app_version, metadata_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id, scoped_workspace_id, organization_id, category, title, description, severity,
                str(payload.get("status") or "open"), str(payload.get("attachment_url") or ""),
                str(payload.get("page_url") or ""), str(payload.get("user_agent") or ""),
                str(payload.get("app_version") or ""), json.dumps(metadata), now, now,
            ),
        )
        feedback_id = int(cur.lastrowid)
        add_audit_log(user_id, "feedback.create", "feedback", str(feedback_id), {"category": category, "severity": severity}, con=con, workspace_id=scoped_workspace_id, organization_id=organization_id)
        return feedback_id


def list_feedback(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        rows = con.execute(
            "SELECT * FROM feedback WHERE user_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, scoped_workspace_id, max(1, min(int(limit), 500))),
        ).fetchall()
    return [dict(r) for r in rows]


def get_feedback(feedback_id: int, user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    with connect() as con:
        if workspace_id is None:
            row = con.execute("SELECT * FROM feedback WHERE id=? AND user_id=?", (feedback_id, user_id)).fetchone()
        else:
            scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
            row = con.execute("SELECT * FROM feedback WHERE id=? AND user_id=? AND workspace_id=?", (feedback_id, user_id, scoped_workspace_id)).fetchone()
    return dict(row) if row else {}


def update_feedback_status(feedback_id: int, user_id: int, status: str, workspace_id: int | None = None) -> None:
    status = str(status or "").strip().lower()
    if status not in FEEDBACK_STATUSES:
        raise ValueError(f"Invalid feedback status: {status}")
    with connect() as con:
        if workspace_id is None:
            row = con.execute("SELECT id, workspace_id, organization_id FROM feedback WHERE id=? AND user_id=?", (feedback_id, user_id)).fetchone()
        else:
            scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
            row = con.execute("SELECT id, workspace_id, organization_id FROM feedback WHERE id=? AND user_id=? AND workspace_id=?", (feedback_id, user_id, scoped_workspace_id)).fetchone()
        if not row:
            raise ValueError("Feedback not found")
        con.execute("UPDATE feedback SET status=?, updated_at=? WHERE id=? AND user_id=?", (status, utc_now(), feedback_id, user_id))
        add_audit_log(user_id, "feedback.update_status", "feedback", str(feedback_id), {"status": status}, con=con, workspace_id=row["workspace_id"], organization_id=row["organization_id"])


def add_audit_log(
    user_id: int | None,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    metadata: Dict[str, Any] | None = None,
    ip_address: str = "",
    user_agent: str = "",
    con=None,
    workspace_id: int | None = None,
    organization_id: int | None = None,
) -> None:
    owns_connection = con is None
    if owns_connection:
        con = sqlite3.connect(db_path())
        con.row_factory = sqlite3.Row
    try:
        try:
            _migrate_audit_scope_columns(con)
        except Exception:
            pass
        con.execute(
            """
            INSERT INTO audit_logs(user_id, action, resource_type, resource_id, ip_address, user_agent, metadata_json, created_at, workspace_id, organization_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (user_id, action, resource_type, resource_id, ip_address, user_agent, json.dumps(metadata or {}), utc_now(), workspace_id, organization_id),
        )
        if owns_connection:
            con.commit()
    finally:
        if owns_connection:
            con.close()


def list_audit_logs(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        if workspace_id is None:
            rows = con.execute(
                "SELECT * FROM audit_logs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, max(1, min(int(limit), 500))),
            ).fetchall()
        else:
            scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
            rows = con.execute(
                "SELECT * FROM audit_logs WHERE user_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, scoped_workspace_id, max(1, min(int(limit), 500))),
            ).fetchall()
    return [dict(r) for r in rows]


def db_health() -> dict[str, Any]:
    started = utc_now()
    with connect() as con:
        con.execute("SELECT 1").fetchone()
        users_count = con.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        feedback_count = con.execute("SELECT COUNT(*) AS count FROM feedback").fetchone()["count"]
        usage_count = con.execute("SELECT COUNT(*) AS count FROM usage_counters").fetchone()["count"]
    return {"status": "ok", "checked_at": started, "users": users_count, "feedback": feedback_count, "usage_counters": usage_count}


def storage_health() -> dict[str, Any]:
    path = db_path()
    stat = path.stat() if path.exists() else None
    return {
        "status": "ok",
        "database_path": str(path),
        "database_exists": path.exists(),
        "database_size_bytes": stat.st_size if stat else 0,
        "data_dir": str(path.parent),
        "data_dir_writable": os.access(path.parent, os.W_OK),
    }


def increment_usage_counter(
    *,
    resource_type: str,
    window_start: str,
    window_end: str,
    user_id: int | None = None,
    ip_address: str = "",
) -> int:
    now = utc_now()
    counter_user_id = int(user_id) if user_id is not None else -1
    with connect() as con:
        con.execute("DELETE FROM usage_counters WHERE window_end < ?", (now,))
        con.execute(
            """
            INSERT INTO usage_counters(user_id, ip_address, resource_type, count, window_start, window_end, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, ip_address, resource_type, window_start)
            DO UPDATE SET count=count + 1, updated_at=excluded.updated_at
            """,
            (counter_user_id, ip_address or "", resource_type, 1, window_start, window_end, now, now),
        )
        row = con.execute(
            "SELECT count FROM usage_counters WHERE user_id=? AND ip_address=? AND resource_type=? AND window_start=?",
            (counter_user_id, ip_address or "", resource_type, window_start),
        ).fetchone()
        return int(row["count"] if row else 1)


def usage_summary(user_id: int | None = None) -> list[dict[str, Any]]:
    now = utc_now()
    with connect() as con:
        if user_id is None:
            rows = con.execute(
                """
                SELECT resource_type, SUM(count) AS count, MIN(window_start) AS window_start, MAX(window_end) AS window_end
                FROM usage_counters
                WHERE window_end >= ?
                GROUP BY resource_type
                ORDER BY resource_type
                """,
                (now,),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT resource_type, SUM(count) AS count, MIN(window_start) AS window_start, MAX(window_end) AS window_end
                FROM usage_counters
                WHERE user_id=? AND window_end >= ?
                GROUP BY resource_type
                ORDER BY resource_type
                """,
                (user_id, now),
            ).fetchall()
    return [dict(row) for row in rows]


def log_ai_generation(user_id: int | None, *, provider: str = "", model: str = "", task_type: str = "general", prompt_version: str = "", prompt_hash: str = "", input_tokens: int = 0, output_tokens: int = 0, estimated_cost: float = 0.0, latency_ms: int | None = None, status: str = "unknown", error_message: str = "", workspace_id: int | None = None) -> int:
    with connect() as con:
        scoped_workspace_id = None
        organization_id = None
        if user_id:
            scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
        cur = con.execute("""
            INSERT INTO ai_generations(user_id, workspace_id, organization_id, provider, model, task_type, prompt_version, prompt_hash, input_tokens, output_tokens, estimated_cost, latency_ms, status, error_message, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (user_id, scoped_workspace_id, organization_id, provider, model, task_type, prompt_version, prompt_hash, int(input_tokens or 0), int(output_tokens or 0), float(estimated_cost or 0), latency_ms, status, error_message, utc_now()))
        return int(cur.lastrowid)


def record_score_feedback(user_id: int, job_id: int, signal: str, workspace_id: int | None = None) -> int:
    """Record a user's relevance signal ('relevant'/'irrelevant') for a scored job."""
    signal = (signal or "").strip().lower()
    if signal not in ("relevant", "irrelevant"):
        raise ValueError("signal must be 'relevant' or 'irrelevant'")
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        cur = con.execute(
            "INSERT INTO score_feedback(user_id, workspace_id, job_id, signal, created_at) VALUES (?,?,?,?,?)",
            (user_id, scoped_workspace_id, job_id, signal, utc_now()),
        )
        return int(cur.lastrowid)


def recent_score_feedback(user_id: int, limit: int = 10, workspace_id: int | None = None) -> list[dict[str, Any]]:
    """Most recent relevance signals for a user, with the job's title/company for context."""
    with connect() as con:
        rows = con.execute(
            """
            SELECT sf.signal, sf.created_at, j.title, j.company
            FROM score_feedback sf
            LEFT JOIN jobs j ON j.id = sf.job_id
            WHERE sf.user_id = ?
            ORDER BY sf.id DESC
            LIMIT ?
            """,
            (user_id, max(1, min(int(limit), 50))),
        ).fetchall()
    return [dict(r) for r in rows]


def count_ai_generations_today(user_id: int) -> int:
    """Count today's (UTC) billable AI generations for a user.

    Only rows that hit a real provider are counted (``provider != 'none'``),
    so local/fallback responses do not consume the user's daily budget.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    with connect() as con:
        row = con.execute(
            """
            SELECT COUNT(*) AS n FROM ai_generations
            WHERE user_id=? AND substr(created_at, 1, 10)=?
              AND provider IS NOT NULL AND provider != '' AND provider != 'none'
            """,
            (user_id, today),
        ).fetchone()
    return int(row["n"]) if row else 0


def list_ai_generations(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        rows = con.execute("SELECT * FROM ai_generations WHERE user_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?", (user_id, scoped_workspace_id, max(1, min(int(limit), 500)))).fetchall()
    return [dict(r) for r in rows]


def upsert_prompt_version(name: str, version: str, template: str, description: str = "", is_active: bool = True) -> None:
    now = utc_now()
    with connect() as con:
        con.execute("""
            INSERT INTO prompt_versions(name, version, description, template, is_active, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(name, version) DO UPDATE SET description=excluded.description, template=excluded.template, is_active=excluded.is_active, updated_at=excluded.updated_at
        """, (name, version, description, template, 1 if is_active else 0, now, now))


def list_prompt_versions(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as con:
        rows = con.execute("SELECT id, name, version, description, is_active, created_at, updated_at FROM prompt_versions ORDER BY name, version LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
    return [dict(r) for r in rows]


def create_automation_rule(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    now = utc_now()
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id or payload.get("workspace_id"))
        cur = con.execute("""
            INSERT INTO automation_rules(user_id, workspace_id, organization_id, name, trigger_event, action_type, conditions_json, action_config_json, is_active, human_approval_required, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (user_id, scoped_workspace_id, organization_id, str(payload.get("name") or "Automation rule"), str(payload.get("trigger_event") or "manual"), str(payload.get("action_type") or "notify"), json.dumps(payload.get("conditions") or {}), json.dumps(payload.get("action_config") or {}), 1 if payload.get("is_active", True) else 0, 1 if payload.get("human_approval_required", True) else 0, now, now))
        rule_id = int(cur.lastrowid)
        add_audit_log(user_id, "automation_rule.create", "automation_rule", str(rule_id), {"trigger_event": payload.get("trigger_event"), "action_type": payload.get("action_type")}, con=con, workspace_id=scoped_workspace_id, organization_id=organization_id)
        return rule_id


def list_automation_rules(user_id: int, include_inactive: bool = False, workspace_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        where = "user_id=? AND workspace_id=?" if include_inactive else "user_id=? AND workspace_id=? AND is_active=1"
        rows = con.execute(f"SELECT * FROM automation_rules WHERE {where} ORDER BY created_at DESC", (user_id, scoped_workspace_id)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["conditions"] = _safe_json_loads(item.pop("conditions_json", "{}"), {})
        item["action_config"] = _safe_json_loads(item.pop("action_config_json", "{}"), {})
        item["is_active"] = bool(item.get("is_active"))
        item["human_approval_required"] = bool(item.get("human_approval_required"))
        out.append(item)
    return out


def update_automation_rule(rule_id: int, user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> None:
    current = next((r for r in list_automation_rules(user_id, include_inactive=True, workspace_id=workspace_id) if int(r["id"]) == int(rule_id)), None)
    if not current:
        raise ValueError("Automation rule not found")
    merged = {**current, **(payload or {})}
    with connect() as con:
        con.execute("""
            UPDATE automation_rules SET name=?, trigger_event=?, action_type=?, conditions_json=?, action_config_json=?, is_active=?, human_approval_required=?, updated_at=?
            WHERE id=? AND user_id=? AND workspace_id=?
        """, (str(merged.get("name") or current["name"]), str(merged.get("trigger_event") or current["trigger_event"]), str(merged.get("action_type") or current["action_type"]), json.dumps(merged.get("conditions") or {}), json.dumps(merged.get("action_config") or {}), 1 if merged.get("is_active", True) else 0, 1 if merged.get("human_approval_required", True) else 0, utc_now(), rule_id, user_id, current["workspace_id"]))
        add_audit_log(user_id, "automation_rule.update", "automation_rule", str(rule_id), {}, con=con, workspace_id=current["workspace_id"], organization_id=current.get("organization_id"))


def delete_automation_rule(rule_id: int, user_id: int, workspace_id: int | None = None) -> None:
    current = next((r for r in list_automation_rules(user_id, include_inactive=True, workspace_id=workspace_id) if int(r["id"]) == int(rule_id)), None)
    with connect() as con:
        if current:
            con.execute("DELETE FROM automation_rules WHERE id=? AND user_id=? AND workspace_id=?", (rule_id, user_id, current["workspace_id"]))
            add_audit_log(user_id, "automation_rule.delete", "automation_rule", str(rule_id), {}, con=con, workspace_id=current["workspace_id"], organization_id=current.get("organization_id"))


def create_automation_run(user_id: int, trigger_event: str, input_payload: Dict[str, Any] | None = None, rule_id: int | None = None, status: str = "pending", workspace_id: int | None = None) -> int:
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
        cur = con.execute("INSERT INTO automation_runs(rule_id, user_id, workspace_id, organization_id, status, trigger_event, input_payload, created_at) VALUES (?,?,?,?,?,?,?,?)", (rule_id, user_id, scoped_workspace_id, organization_id, status, trigger_event, json.dumps(input_payload or {}), utc_now()))
        return int(cur.lastrowid)


def update_automation_run(run_id: int, user_id: int, *, status: str, output_payload: Dict[str, Any] | None = None, error_message: str = "") -> None:
    now = utc_now()
    completed = now if status in {"completed", "failed", "cancelled", "requires_approval"} else None
    with connect() as con:
        con.execute("UPDATE automation_runs SET status=?, output_payload=?, error_message=?, started_at=COALESCE(started_at, ?), completed_at=COALESCE(?, completed_at) WHERE id=? AND user_id=?", (status, json.dumps(output_payload or {}), error_message, now, completed, run_id, user_id))


def list_automation_runs(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        rows = con.execute("SELECT * FROM automation_runs WHERE user_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?", (user_id, scoped_workspace_id, max(1, min(int(limit), 500)))).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["input_payload"] = _safe_json_loads(item.get("input_payload"), {})
        item["output_payload"] = _safe_json_loads(item.get("output_payload"), {})
        out.append(item)
    return out


def add_automation_error(user_id: int | None, run_id: int | None, error_message: str, error_type: str = "runtime", metadata: Dict[str, Any] | None = None, workspace_id: int | None = None) -> None:
    with connect() as con:
        scoped_workspace_id = None
        organization_id = None
        if run_id:
            row = con.execute("SELECT workspace_id, organization_id FROM automation_runs WHERE id=?", (run_id,)).fetchone()
            if row:
                scoped_workspace_id, organization_id = row["workspace_id"], row["organization_id"]
        elif user_id:
            scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id)
        con.execute("INSERT INTO automation_errors(run_id, user_id, workspace_id, organization_id, error_type, error_message, metadata_json, created_at) VALUES (?,?,?,?,?,?,?,?)", (run_id, user_id, scoped_workspace_id, organization_id, error_type, error_message, json.dumps(metadata or {}), utc_now()))


def list_automation_errors(user_id: int, limit: int = 100, workspace_id: int | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        rows = con.execute("SELECT * FROM automation_errors WHERE user_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?", (user_id, scoped_workspace_id, max(1, min(int(limit), 500)))).fetchall()
    return [dict(r) for r in rows]


def create_post(user_id: int, payload: Dict[str, Any], workspace_id: int | None = None) -> int:
    now = utc_now()
    with connect() as con:
        scoped_workspace_id, organization_id = _workspace_scope_for_user(con, user_id, workspace_id or payload.get("workspace_id"))
        cur = con.execute("""
            INSERT INTO posts(user_id, workspace_id, organization_id, title, base_content, status, scheduled_at, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (user_id, scoped_workspace_id, organization_id, payload.get("title") or "", payload.get("base_content") or payload.get("content") or "", payload.get("status") or "draft", payload.get("scheduled_at") or None, now, now))
        post_id = int(cur.lastrowid)
        for target in payload.get("targets") or []:
            con.execute("""
                INSERT INTO post_targets(post_id, platform, provider_name, transformed_content, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
            """, (post_id, target.get("platform") or "", target.get("provider_name") or "", target.get("transformed_content") or payload.get("base_content") or payload.get("content") or "", target.get("status") or "pending", now, now))
        add_audit_log(user_id, "post.create", "post", str(post_id), {"status": payload.get("status") or "draft"}, con=con, workspace_id=scoped_workspace_id, organization_id=organization_id)
        return post_id


def list_posts(user_id: int, workspace_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with connect() as con:
        scoped_workspace_id, _ = _workspace_scope_for_user(con, user_id, workspace_id)
        rows = con.execute("SELECT * FROM posts WHERE user_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?", (user_id, scoped_workspace_id, max(1, min(int(limit), 500)))).fetchall()
        posts = []
        for row in rows:
            item = dict(row)
            targets = con.execute("SELECT * FROM post_targets WHERE post_id=? ORDER BY id", (item["id"],)).fetchall()
            item["targets"] = [dict(t) for t in targets]
            posts.append(item)
        return posts



def delete_user_data(user_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM reminders WHERE job_id IN (SELECT id FROM jobs WHERE user_id=?)", (user_id,))
        con.execute("DELETE FROM application_materials WHERE job_id IN (SELECT id FROM jobs WHERE user_id=?)", (user_id,))
        con.execute("DELETE FROM evaluations WHERE job_id IN (SELECT id FROM jobs WHERE user_id=?)", (user_id,))
        con.execute("DELETE FROM applications WHERE job_id IN (SELECT id FROM jobs WHERE user_id=?)", (user_id,))
        con.execute("DELETE FROM jobs WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM profile WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM integration_settings WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM automation_preferences WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM activity_events WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM feedback WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM audit_logs WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM ai_generations WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM automation_errors WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM automation_steps WHERE run_id IN (SELECT id FROM automation_runs WHERE user_id=?)", (user_id,))
        con.execute("DELETE FROM automation_runs WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM automation_rules WHERE user_id=?", (user_id,))


def delete_all_data(user_id: int = 1) -> None:
    delete_user_data(user_id)


# ---------------------------------------------------------------------------
# Milestone 7: team, workspace, RBAC, sharing, and admin foundations
# ---------------------------------------------------------------------------
SYSTEM_ROLES = [
    ("owner", "Full control over an organization/workspace."),
    ("admin", "Manage members, integrations, and workspace configuration."),
    ("manager", "Manage workflows and review team resources."),
    ("editor", "Create and edit content and workflow resources."),
    ("recruiter", "Manage opportunities and recruiting workflows."),
    ("moderator", "Review shared content and feedback."),
    ("analyst", "View analytics, audit activity, and reports."),
    ("contributor", "Create resources but cannot manage settings."),
    ("viewer", "Read-only workspace access."),
]

SYSTEM_PERMISSIONS = {
    "workspace:manage": "Manage workspace settings.",
    "workspace:invite": "Invite or add members to a workspace.",
    "member:read": "View workspace members.",
    "feedback:create": "Create feedback.",
    "feedback:read_all": "Read workspace feedback.",
    "integration:manage": "Manage provider and integration credentials.",
    "provider:manage": "Manage provider abstraction records.",
    "post:create": "Create draft publishing content.",
    "post:approve": "Approve content before publishing.",
    "post:publish": "Publish content through connected providers.",
    "automation:create": "Create automation rules.",
    "automation:run": "Run automation workflows.",
    "automation:disable": "Disable automation workflows.",
    "audit_log:view": "View audit logs.",
    "ai:generate": "Generate AI content.",
    "billing:manage": "Manage billing configuration.",
    "user:invite": "Invite users.",
    "shared_resource:create": "Share resources into a workspace.",
    "shared_resource:read": "Read shared workspace resources.",
}

ROLE_PERMISSION_MAP = {
    "owner": list(SYSTEM_PERMISSIONS.keys()),
    "admin": [p for p in SYSTEM_PERMISSIONS if p != "billing:manage"],
    "manager": ["member:read", "feedback:read_all", "post:create", "post:approve", "automation:create", "automation:run", "automation:disable", "audit_log:view", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "editor": ["post:create", "automation:run", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "recruiter": ["post:create", "automation:run", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "moderator": ["member:read", "feedback:read_all", "post:approve", "shared_resource:read"],
    "analyst": ["member:read", "audit_log:view", "shared_resource:read"],
    "contributor": ["post:create", "ai:generate", "shared_resource:create", "shared_resource:read"],
    "viewer": ["shared_resource:read"],
}


def _slugify(value: str) -> str:
    text = ''.join(ch.lower() if ch.isalnum() else '-' for ch in (value or '').strip())
    while '--' in text:
        text = text.replace('--', '-')
    return text.strip('-') or f"item-{secrets.token_hex(4)}"


def _seed_roles_permissions(con) -> None:
    now = utc_now()
    for role, description in SYSTEM_ROLES:
        con.execute(
            "INSERT OR IGNORE INTO roles(name, description, is_system, created_at, updated_at) VALUES (?,?,?,?,?)",
            (role, description, 1, now, now),
        )
    for perm, description in SYSTEM_PERMISSIONS.items():
        con.execute(
            "INSERT OR IGNORE INTO permissions(name, description, created_at) VALUES (?,?,?)",
            (perm, description, now),
        )
    for role, permissions in ROLE_PERMISSION_MAP.items():
        for perm in permissions:
            con.execute(
                "INSERT OR IGNORE INTO role_permissions(role_name, permission_name, created_at) VALUES (?,?,?)",
                (role, perm, now),
            )


def _migrate_audit_scope_columns(con) -> None:
    cols = _table_columns(con, "audit_logs")
    if "workspace_id" not in cols:
        con.execute("ALTER TABLE audit_logs ADD COLUMN workspace_id INTEGER")
    if "organization_id" not in cols:
        con.execute("ALTER TABLE audit_logs ADD COLUMN organization_id INTEGER")


def _ensure_personal_workspace_for_all_users(con) -> None:
    users = con.execute("SELECT id, email, full_name FROM users WHERE is_active=1").fetchall()
    for user in users:
        _ensure_personal_workspace(con, int(user["id"]), user["email"], user["full_name"] or "")


def _ensure_personal_workspace(con, user_id: int, email: str = "", full_name: str = "") -> dict[str, Any]:
    existing = con.execute(
        """
        SELECT o.id AS organization_id, o.name AS organization_name, w.id AS workspace_id, w.name AS workspace_name
        FROM workspace_members wm
        JOIN workspaces w ON w.id = wm.workspace_id
        JOIN organizations o ON o.id = w.organization_id
        WHERE wm.user_id=? AND wm.role='owner'
        ORDER BY wm.created_at ASC LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if existing:
        return dict(existing)
    now = utc_now()
    owner_label = full_name.strip() or (email.split('@')[0] if email else f"User {user_id}")
    org_name = f"{owner_label}'s Organization"
    org_slug_base = _slugify(f"{owner_label}-{user_id}")
    org_slug = org_slug_base
    suffix = 1
    while con.execute("SELECT 1 FROM organizations WHERE slug=?", (org_slug,)).fetchone():
        suffix += 1
        org_slug = f"{org_slug_base}-{suffix}"
    org_cur = con.execute(
        "INSERT INTO organizations(name, slug, owner_user_id, created_at, updated_at) VALUES (?,?,?,?,?)",
        (org_name, org_slug, user_id, now, now),
    )
    org_id = int(org_cur.lastrowid)
    ws_cur = con.execute(
        "INSERT INTO workspaces(organization_id, name, slug, description, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (org_id, "Personal Workspace", "personal", "Default private workspace", now, now),
    )
    workspace_id = int(ws_cur.lastrowid)
    con.execute(
        "INSERT OR IGNORE INTO workspace_members(workspace_id, user_id, role, status, invited_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (workspace_id, user_id, "owner", "active", user_id, now, now),
    )
    return {"organization_id": org_id, "organization_name": org_name, "workspace_id": workspace_id, "workspace_name": "Personal Workspace"}


def ensure_user_workspace(user_id: int) -> dict[str, Any]:
    with connect() as con:
        user = con.execute("SELECT id, email, full_name FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise ValueError("User not found")
        _seed_roles_permissions(con)
        _migrate_audit_scope_columns(con)
        workspace = _ensure_personal_workspace(con, user_id, user["email"], user["full_name"] or "")
        return workspace


def list_roles() -> list[dict[str, Any]]:
    with connect() as con:
        _seed_roles_permissions(con)
        rows = con.execute("SELECT * FROM roles ORDER BY CASE name WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 WHEN 'manager' THEN 3 ELSE 9 END, name").fetchall()
    return [dict(r) for r in rows]


def list_permissions() -> list[dict[str, Any]]:
    with connect() as con:
        _seed_roles_permissions(con)
        rows = con.execute("SELECT * FROM permissions ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def list_role_permissions(role_name: str | None = None) -> list[dict[str, Any]]:
    with connect() as con:
        _seed_roles_permissions(con)
        if role_name:
            rows = con.execute("SELECT * FROM role_permissions WHERE role_name=? ORDER BY permission_name", (role_name,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM role_permissions ORDER BY role_name, permission_name").fetchall()
    return [dict(r) for r in rows]


def create_organization(user_id: int, name: str) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Organization name is required")
    now = utc_now()
    slug_base = _slugify(name)
    slug = slug_base
    with connect() as con:
        suffix = 1
        while con.execute("SELECT 1 FROM organizations WHERE slug=?", (slug,)).fetchone():
            suffix += 1
            slug = f"{slug_base}-{suffix}"
        cur = con.execute(
            "INSERT INTO organizations(name, slug, owner_user_id, created_at, updated_at) VALUES (?,?,?,?,?)",
            (name, slug, user_id, now, now),
        )
        org_id = int(cur.lastrowid)
        add_audit_log(user_id, "organization.create", "organization", str(org_id), {"name": name}, con=con, organization_id=org_id)
        return {"id": org_id, "name": name, "slug": slug, "owner_user_id": user_id, "created_at": now, "updated_at": now}


def create_workspace(user_id: int, organization_id: int, name: str, description: str = "") -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Workspace name is required")
    now = utc_now()
    slug_base = _slugify(name)
    slug = slug_base
    with connect() as con:
        org = con.execute("SELECT * FROM organizations WHERE id=?", (organization_id,)).fetchone()
        if not org:
            raise ValueError("Organization not found")
        if int(org["owner_user_id"]) != int(user_id) and not user_has_permission(user_id, None, "workspace:manage", organization_id=organization_id, con=con):
            raise PermissionError("You do not have permission to create workspaces in this organization")
        suffix = 1
        while con.execute("SELECT 1 FROM workspaces WHERE organization_id=? AND slug=?", (organization_id, slug)).fetchone():
            suffix += 1
            slug = f"{slug_base}-{suffix}"
        cur = con.execute(
            "INSERT INTO workspaces(organization_id, name, slug, description, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (organization_id, name, slug, description or "", now, now),
        )
        workspace_id = int(cur.lastrowid)
        con.execute(
            "INSERT OR IGNORE INTO workspace_members(workspace_id, user_id, role, status, invited_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (workspace_id, user_id, "owner", "active", user_id, now, now),
        )
        add_audit_log(user_id, "workspace.create", "workspace", str(workspace_id), {"name": name}, con=con, workspace_id=workspace_id, organization_id=organization_id)
        return {"id": workspace_id, "organization_id": organization_id, "name": name, "slug": slug, "description": description or "", "created_at": now, "updated_at": now}


def list_user_workspaces(user_id: int) -> list[dict[str, Any]]:
    ensure_user_workspace(user_id)
    with connect() as con:
        rows = con.execute(
            """
            SELECT w.*, o.name AS organization_name, o.slug AS organization_slug, wm.role, wm.status
            FROM workspace_members wm
            JOIN workspaces w ON w.id = wm.workspace_id
            JOIN organizations o ON o.id = w.organization_id
            WHERE wm.user_id=? AND wm.status='active'
            ORDER BY o.name, w.name
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_workspace_for_user(user_id: int, workspace_id: int) -> dict[str, Any]:
    with connect() as con:
        row = con.execute(
            """
            SELECT w.*, o.name AS organization_name, wm.role
            FROM workspace_members wm
            JOIN workspaces w ON w.id=wm.workspace_id
            JOIN organizations o ON o.id=w.organization_id
            WHERE wm.user_id=? AND wm.workspace_id=? AND wm.status='active'
            """,
            (user_id, workspace_id),
        ).fetchone()
    return dict(row) if row else {}


def list_workspace_members(user_id: int, workspace_id: int) -> list[dict[str, Any]]:
    if not user_has_permission(user_id, workspace_id, "member:read") and not user_has_permission(user_id, workspace_id, "workspace:manage"):
        raise PermissionError("You do not have permission to view workspace members")
    with connect() as con:
        rows = con.execute(
            """
            SELECT wm.id, wm.workspace_id, wm.user_id, u.email, u.full_name, wm.role, wm.status, wm.invited_by, wm.created_at, wm.updated_at
            FROM workspace_members wm
            JOIN users u ON u.id=wm.user_id
            WHERE wm.workspace_id=?
            ORDER BY CASE wm.role WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 ELSE 9 END, u.email
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_workspace_member(actor_user_id: int, workspace_id: int, email: str, role: str = "viewer") -> dict[str, Any]:
    role = (role or "viewer").strip().lower()
    email = (email or "").strip().lower()
    if role not in {r[0] for r in SYSTEM_ROLES}:
        raise ValueError("Invalid role")
    if not email:
        raise ValueError("Member email is required")
    if not user_has_permission(actor_user_id, workspace_id, "workspace:invite") and not user_has_permission(actor_user_id, workspace_id, "workspace:manage"):
        raise PermissionError("You do not have permission to add workspace members")
    now = utc_now()
    with connect() as con:
        user = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            raise ValueError("User must create an account before they can be added to a workspace")
        target_user_id = int(user["id"])
        con.execute(
            """
            INSERT INTO workspace_members(workspace_id, user_id, role, status, invited_by, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(workspace_id, user_id) DO UPDATE SET role=excluded.role, status='active', invited_by=excluded.invited_by, updated_at=excluded.updated_at
            """,
            (workspace_id, target_user_id, role, "active", actor_user_id, now, now),
        )
        ws = con.execute("SELECT organization_id FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        add_audit_log(actor_user_id, "workspace_member.upsert", "workspace_member", str(target_user_id), {"workspace_id": workspace_id, "role": role, "email": email}, con=con, workspace_id=workspace_id, organization_id=int(ws["organization_id"]) if ws else None)
        return {"workspace_id": workspace_id, "user_id": target_user_id, "email": email, "role": role, "status": "active"}


def user_has_permission(user_id: int, workspace_id: int | None, permission_name: str, *, organization_id: int | None = None, con=None) -> bool:
    close_conn = False
    if con is None:
        con = sqlite3.connect(db_path())
        con.row_factory = sqlite3.Row
        close_conn = True
    try:
        _seed_roles_permissions(con)
        if workspace_id is not None:
            rows = con.execute(
                """
                SELECT rp.permission_name
                FROM workspace_members wm
                JOIN role_permissions rp ON rp.role_name=wm.role
                WHERE wm.user_id=? AND wm.workspace_id=? AND wm.status='active'
                """,
                (user_id, workspace_id),
            ).fetchall()
        elif organization_id is not None:
            rows = con.execute(
                """
                SELECT rp.permission_name
                FROM workspace_members wm
                JOIN workspaces w ON w.id=wm.workspace_id
                JOIN role_permissions rp ON rp.role_name=wm.role
                WHERE wm.user_id=? AND w.organization_id=? AND wm.status='active'
                """,
                (user_id, organization_id),
            ).fetchall()
        else:
            rows = []
        return any(r["permission_name"] == permission_name for r in rows)
    finally:
        if close_conn:
            con.close()


def share_resource(user_id: int, workspace_id: int, resource_type: str, resource_id: str, access_level: str = "read", expires_at: str = "") -> int:
    resource_type = (resource_type or "").strip().lower()
    resource_id = (resource_id or "").strip()
    access_level = (access_level or "read").strip().lower()
    if not resource_type or not resource_id:
        raise ValueError("resource_type and resource_id are required")
    if access_level not in {"read", "comment", "edit", "admin"}:
        access_level = "read"
    if not user_has_permission(user_id, workspace_id, "shared_resource:create"):
        raise PermissionError("You do not have permission to share resources in this workspace")
    with connect() as con:
        ws = con.execute("SELECT organization_id FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        now = utc_now()
        cur = con.execute(
            """
            INSERT INTO shared_resources(user_id, workspace_id, resource_type, resource_id, access_level, created_at, expires_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(workspace_id, resource_type, resource_id) DO UPDATE SET access_level=excluded.access_level, expires_at=excluded.expires_at
            """,
            (user_id, workspace_id, resource_type, resource_id, access_level, now, expires_at or None),
        )
        row = con.execute("SELECT id FROM shared_resources WHERE workspace_id=? AND resource_type=? AND resource_id=?", (workspace_id, resource_type, resource_id)).fetchone()
        share_id = int(row["id"] if row else cur.lastrowid)
        add_audit_log(user_id, "shared_resource.upsert", "shared_resource", str(share_id), {"resource_type": resource_type, "resource_id": resource_id, "access_level": access_level}, con=con, workspace_id=workspace_id, organization_id=int(ws["organization_id"]) if ws else None)
        return share_id


def list_shared_resources(user_id: int, workspace_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    workspaces = list_user_workspaces(user_id)
    allowed_workspace_ids = {int(w["id"]) for w in workspaces if user_has_permission(user_id, int(w["id"]), "shared_resource:read")}
    if workspace_id is not None:
        if int(workspace_id) not in allowed_workspace_ids:
            raise PermissionError("You do not have access to this workspace")
        allowed_workspace_ids = {int(workspace_id)}
    if not allowed_workspace_ids:
        return []
    placeholders = ','.join(['?'] * len(allowed_workspace_ids))
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT sr.*, w.name AS workspace_name, o.name AS organization_name, u.email AS shared_by_email
            FROM shared_resources sr
            JOIN workspaces w ON w.id=sr.workspace_id
            JOIN organizations o ON o.id=w.organization_id
            JOIN users u ON u.id=sr.user_id
            WHERE sr.workspace_id IN ({placeholders})
            ORDER BY sr.created_at DESC LIMIT ?
            """,
            [*allowed_workspace_ids, max(1, min(int(limit), 500))],
        ).fetchall()
    return [dict(r) for r in rows]


def enterprise_summary(user_id: int) -> dict[str, Any]:
    ensure_user_workspace(user_id)
    workspaces = list_user_workspaces(user_id)
    workspace_ids = [int(w["id"]) for w in workspaces]
    with connect() as con:
        if workspace_ids:
            placeholders = ','.join(['?'] * len(workspace_ids))
            member_count = con.execute(f"SELECT COUNT(DISTINCT user_id) AS count FROM workspace_members WHERE workspace_id IN ({placeholders})", workspace_ids).fetchone()["count"]
            shared_count = con.execute(f"SELECT COUNT(*) AS count FROM shared_resources WHERE workspace_id IN ({placeholders})", workspace_ids).fetchone()["count"]
            audit_count = con.execute("SELECT COUNT(*) AS count FROM audit_logs WHERE user_id=?", (user_id,)).fetchone()["count"]
        else:
            member_count = shared_count = audit_count = 0
    return {
        "workspaces": len(workspaces),
        "members": int(member_count or 0),
        "shared_resources": int(shared_count or 0),
        "audit_events": int(audit_count or 0),
        "roles": len(SYSTEM_ROLES),
        "permissions": len(SYSTEM_PERMISSIONS),
    }
