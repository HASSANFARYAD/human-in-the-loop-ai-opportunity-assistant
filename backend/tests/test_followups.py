from __future__ import annotations

import sqlite3

from job_assistant import followups
from job_assistant.config import settings
from test_agent_chat_api import _client
from test_jobs_api import _job_payload as _job_payload_base


def _job_payload(title: str) -> dict:
    return _job_payload_base(title, "job")


def _backdate_application(db_path, job_id: int, iso: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE applications SET last_updated=? WHERE job_id=?", (iso, job_id))


def _setup_applied_job(client, headers, db_path, title: str) -> int:
    created = client.post("/api/v1/jobs", json=_job_payload(title), headers=headers)
    assert created.status_code == 200
    job_id = created.json()["id"]
    from job_assistant.db import update_status

    update_status(job_id, "Applied", user_id=1)
    return job_id


def test_followup_created_for_stale_applied_job(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    db_path = tmp_path / "agent.sqlite3"
    job_id = _setup_applied_job(client, headers, db_path, "Backend Engineer")
    _backdate_application(db_path, job_id, "2026-01-01T00:00:00+00:00")

    from job_assistant.db import create_followup_reminders, due_reminders

    assert create_followup_reminders(after_days=7) == 1
    reminders = due_reminders(1)
    assert any(r["kind"] == "followup" for r in reminders)

    # Idempotent: a second pass does not duplicate the open reminder.
    assert create_followup_reminders(after_days=7) == 0


def test_no_followup_for_recent_applied_job(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    db_path = tmp_path / "agent.sqlite3"
    _setup_applied_job(client, headers, db_path, "Recent Role")  # last_updated = now

    from job_assistant.db import create_followup_reminders

    assert create_followup_reminders(after_days=7) == 0


def test_no_followup_for_non_applied_job(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    db_path = tmp_path / "agent.sqlite3"
    created = client.post("/api/v1/jobs", json=_job_payload("Untouched"), headers=headers)
    job_id = created.json()["id"]
    _backdate_application(db_path, job_id, "2026-01-01T00:00:00+00:00")  # no application row yet -> no-op

    from job_assistant.db import create_followup_reminders

    assert create_followup_reminders(after_days=7) == 0


def test_run_followups_never_raises(monkeypatch):
    def _boom(**k):
        raise RuntimeError("db down")

    monkeypatch.setattr(followups, "create_followup_reminders", _boom)
    assert followups.run_followups() == 0


def test_start_scheduler_respects_disabled_flag(monkeypatch):
    monkeypatch.setattr(settings, "followup_reminders_enabled", False)
    followups.start_followup_scheduler()
    assert followups._scheduler is None
