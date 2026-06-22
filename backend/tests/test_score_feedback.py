from __future__ import annotations

import sqlite3

from job_assistant.services import scoring
from test_agent_chat_api import _client
from test_jobs_api import _job_payload as _job_payload_base


def _job_payload(title: str) -> dict:
    return _job_payload_base(title, "job")


def test_calibration_block_empty_without_user(monkeypatch):
    assert scoring._feedback_calibration_block(None) == ""


def test_calibration_block_empty_when_no_signals(monkeypatch):
    monkeypatch.setattr("job_assistant.db.recent_score_feedback", lambda *a, **k: [])
    assert scoring._feedback_calibration_block(1) == ""


def test_calibration_block_formats_signals(monkeypatch):
    monkeypatch.setattr(
        "job_assistant.db.recent_score_feedback",
        lambda *a, **k: [
            {"signal": "relevant", "title": "Backend Engineer", "company": "Acme"},
            {"signal": "irrelevant", "title": "Sales Rep", "company": "Beta"},
        ],
    )
    block = scoring._feedback_calibration_block(1)
    assert "RELEVANT: Backend Engineer Acme" in block
    assert "IRRELEVANT: Sales Rep Beta" in block


def test_calibration_block_survives_db_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("job_assistant.db.recent_score_feedback", _boom)
    assert scoring._feedback_calibration_block(1) == ""


def test_score_opportunity_injects_calibration(monkeypatch):
    captured = {}

    def _fake_ask_json(system, user, fallback, **kwargs):
        captured["user"] = user
        return dict(fallback)

    monkeypatch.setattr(scoring, "ask_json", _fake_ask_json)
    monkeypatch.setattr(
        "job_assistant.db.recent_score_feedback",
        lambda *a, **k: [{"signal": "irrelevant", "title": "Crypto Scam", "company": "Z"}],
    )
    scoring.score_opportunity({"skills": "python"}, {"title": "Dev", "company": "X"}, opp_type="job", user_id=7)
    assert "IRRELEVANT: Crypto Scam Z" in captured["user"]


def _add_score_feedback_table(db_path) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS score_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER,
                job_id INTEGER,
                signal TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def test_score_feedback_endpoint_roundtrip(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    _add_score_feedback_table(tmp_path / "agent.sqlite3")

    created = client.post("/api/v1/jobs", json=_job_payload("Backend Engineer"), headers=headers)
    assert created.status_code == 200
    job_id = created.json()["id"]

    ok = client.post(f"/api/v1/jobs/{job_id}/score-feedback", json={"signal": "irrelevant"}, headers=headers)
    assert ok.status_code == 200
    assert ok.json()["signal"] == "irrelevant"

    from job_assistant.db import recent_score_feedback
    signals = recent_score_feedback(1)
    assert signals and signals[0]["signal"] == "irrelevant"


def test_score_feedback_rejects_bad_signal(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    _add_score_feedback_table(tmp_path / "agent.sqlite3")
    created = client.post("/api/v1/jobs", json=_job_payload("Sales Rep"), headers=headers)
    job_id = created.json()["id"]
    bad = client.post(f"/api/v1/jobs/{job_id}/score-feedback", json={"signal": "meh"}, headers=headers)
    assert bad.status_code == 400
