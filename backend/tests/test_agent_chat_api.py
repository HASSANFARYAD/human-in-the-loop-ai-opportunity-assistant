from __future__ import annotations

from fastapi.testclient import TestClient

from test_jobs_api import _create_minimal_schema


def _client(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.sqlite3"
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    from job_assistant.config import Environment, settings
    import api_server

    settings.db_path = str(db_path)
    settings.environment = Environment.DEV
    settings.database_url = None
    settings.rate_limits_enabled = False
    settings.scheduler_enabled = False
    _create_minimal_schema(db_path)
    client = TestClient(api_server.app)
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "agent@example.com", "password": "StrongerPass123!", "full_name": "Agent User"},
    )
    assert registered.status_code == 200
    return client, {"Authorization": f"Bearer {registered.json()['access_token']}"}


def test_agent_chat_routes_to_chat(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    import job_assistant.api as api

    monkeypatch.setattr(api, "classify_intent", lambda *a, **k: {"intents": ["chat"], "search_query": "", "job_reference": "", "reply": "Hi! How can I help?"})

    resp = client.post("/api/v1/agent/chat", json={"message": "hello"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["intents"] == ["chat"]
    assert body["sections"][0]["message"] == "Hi! How can I help?"


def test_agent_chat_routes_to_job_search(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    import job_assistant.api as api

    monkeypatch.setattr(api, "classify_intent", lambda *a, **k: {"intents": ["job_search"], "search_query": "backend", "job_reference": "", "reply": ""})
    monkeypatch.setattr(api, "run_job_search", lambda *a, **k: [{"title": "Backend Engineer", "company": "Acme", "match_score": 88}])

    resp = client.post("/api/v1/agent/chat", json={"message": "find me backend jobs"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["intents"] == ["job_search"]
    section = body["sections"][0]
    assert section["type"] == "listings"
    assert section["data"][0]["title"] == "Backend Engineer"


def test_agent_chat_tailor_without_job_returns_error(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    import job_assistant.api as api

    monkeypatch.setattr(api, "classify_intent", lambda *a, **k: {"intents": ["tailor_resume"], "search_query": "", "job_reference": "Trilogy", "reply": ""})

    resp = client.post("/api/v1/agent/chat", json={"message": "tailor my resume for Trilogy"}, headers=headers)
    assert resp.status_code == 200
    section = resp.json()["sections"][0]
    assert section["type"] == "error"  # no saved jobs yet


def test_agent_chat_requires_auth(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/agent/chat", json={"message": "hello"})
    assert resp.status_code in (401, 403)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    import json

    events = []
    for block in text.strip().split("\n\n"):
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event:
            events.append((event, data))
    return events


def test_agent_chat_stream_emits_intents_section_done(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    import job_assistant.api as api

    monkeypatch.setattr(api, "classify_intent", lambda *a, **k: {"intents": ["job_search"], "search_query": "go", "job_reference": "", "reply": ""})
    monkeypatch.setattr(api, "run_job_search", lambda *a, **k: [{"title": "Go Dev", "company": "Acme", "match_score": 77}])

    resp = client.post("/api/v1/agent/chat/stream", json={"message": "find jobs"}, headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    names = [e[0] for e in events]
    assert names == ["intents", "section", "done"]
    assert events[0][1]["intents"] == ["job_search"]
    assert events[1][1]["type"] == "listings"
    assert events[1][1]["data"][0]["title"] == "Go Dev"


def test_agent_chat_stream_section_error_is_isolated(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    import job_assistant.api as api

    monkeypatch.setattr(api, "classify_intent", lambda *a, **k: {"intents": ["job_search"], "search_query": "x", "job_reference": "", "reply": ""})

    def _boom(*a, **k):
        raise RuntimeError("discovery down")

    monkeypatch.setattr(api, "run_job_search", _boom)
    resp = client.post("/api/v1/agent/chat/stream", json={"message": "find jobs"}, headers=headers)
    events = _parse_sse(resp.text)
    section = next(e[1] for e in events if e[0] == "section")
    assert section["type"] == "error"
    assert [e[0] for e in events][-1] == "done"  # stream still completes cleanly
