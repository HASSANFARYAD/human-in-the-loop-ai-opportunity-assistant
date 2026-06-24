from __future__ import annotations

from job_assistant import agent_chat


def test_classify_intent_normalizes_and_defaults(monkeypatch):
    monkeypatch.setattr(
        agent_chat.ai_orchestrator,
        "ask_tool_json",
        lambda *a, **k: {"intents": ["job_search", "bogus"], "search_query": " .NET remote ", "job_reference": ""},
    )
    out = agent_chat.classify_intent("find me jobs")
    assert out["intents"] == ["job_search"]  # bogus dropped
    assert out["search_query"] == ".NET remote"


def test_classify_intent_falls_back_to_chat(monkeypatch):
    monkeypatch.setattr(agent_chat.ai_orchestrator, "ask_tool_json", lambda *a, **k: {"intents": []})
    out = agent_chat.classify_intent("hello")
    assert out["intents"] == ["chat"]


def test_run_job_search_scores_and_sorts(monkeypatch):
    monkeypatch.setattr(
        agent_chat,
        "discover_public_opportunities",
        lambda **k: [
            {"title": "A", "company": "X", "url": "u1"},
            {"title": "B", "company": "Y", "url": "u2"},
        ],
    )
    scores = {"A": 40, "B": 90}
    monkeypatch.setattr(agent_chat, "score_job", lambda profile, opp, user_id=None: {"match_score": scores[opp["title"]], "priority": "High"})

    results = agent_chat.run_job_search({"target_roles": "Engineer"}, "engineer", user_id=1)
    assert [r["title"] for r in results] == ["B", "A"]  # sorted by score desc
    assert results[0]["match_score"] == 90


def test_run_job_search_empty_query_no_profile():
    assert agent_chat.run_job_search({}, "") == []


def test_run_job_search_survives_scoring_error(monkeypatch):
    monkeypatch.setattr(agent_chat, "discover_public_opportunities", lambda **k: [{"title": "A", "company": "X"}])

    def _boom(*a, **k):
        raise RuntimeError("scorer down")

    monkeypatch.setattr(agent_chat, "score_job", _boom)
    results = agent_chat.run_job_search({"skills": "python"}, "python", user_id=1)
    assert len(results) == 1
    assert results[0]["match_score"] == 0
