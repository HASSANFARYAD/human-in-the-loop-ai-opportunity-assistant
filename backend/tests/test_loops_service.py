from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from job_assistant.services.loops import execute_loop, check_and_run_due_loops, get_loop_status
from job_assistant.services.auto_apply_pipeline import (
    execute_auto_apply_pipeline, _classify_channel, _discover_jobs,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _fake_pipeline_result(**overrides):
    return {
        "status": "completed", "jobs_discovered": 10, "jobs_qualified": 5,
        "applications_attempted": 3, "applications_submitted": 3,
        "applications_failed": 0, "budget_consumed": 3, "errors": [],
        **overrides,
    }


def _raise(exc: Exception):
    """Return a callable that raises the given exception (replaces side_effect)."""
    def _fn(*args, **kwargs):
        raise exc
    return _fn


# ── Tests: services.loops ───────────────────────────────────────────────────

class TestExecuteLoop:
    def test_loop_not_found(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_loop", lambda *a, **kw: None)
        with pytest.raises(ValueError, match="not found"):
            execute_loop(999, 1)

    def test_loop_inactive(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_loop", lambda *a, **kw: {"is_active": False})
        with pytest.raises(ValueError, match="is inactive"):
            execute_loop(1, 1)

    def test_loop_budget_exhausted(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_loop", lambda *a, **kw: {
            "is_active": True, "auto_apply_enabled": True, "daily_budget": 10, "loop_id": 1,
            "search_query": "engineer", "sources": [], "platforms": [], "channels": ["linkedin"],
            "min_score_threshold": 60, "max_applications_per_run": 5,
        })
        monkeypatch.setattr("job_assistant.services.loops.get_loop_daily_usage", lambda *a, **kw: 10)
        result = execute_loop(1, 1)
        assert result["status"] == "budget_exhausted"

    def test_loop_successful_run(self, monkeypatch):
        loop = {
            "is_active": True, "auto_apply_enabled": True, "daily_budget": 10,
            "loop_id": 1, "search_query": "senior engineer", "sources": ["RemoteJobs.org"],
            "platforms": ["linkedin"], "channels": ["linkedin"],
            "min_score_threshold": 60, "max_applications_per_run": 5, "last_run_at": None,
            "schedule_interval_hours": 6,
        }
        monkeypatch.setattr("job_assistant.services.loops.get_loop", lambda *a, **kw: loop)
        monkeypatch.setattr("job_assistant.services.loops.get_loop_daily_usage", lambda *a, **kw: 2)
        monkeypatch.setattr("job_assistant.services.loops.execute_auto_apply_pipeline",
                           lambda **kw: _fake_pipeline_result())
        monkeypatch.setattr("job_assistant.services.loops.create_loop_run", lambda *a, **kw: 100)
        monkeypatch.setattr("job_assistant.services.loops.update_loop_run", lambda *a, **kw: None)
        monkeypatch.setattr("job_assistant.services.loops.update_loop", lambda *a, **kw: None)

        result = execute_loop(1, 1)
        assert result["status"] == "completed"
        assert result["run_id"] == 100
        assert result["jobs_discovered"] == 10
        assert result["budget_consumed"] == 3

    def test_loop_handles_pipeline_error(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_loop", lambda *a, **kw: {
            "is_active": True, "auto_apply_enabled": True, "daily_budget": 10,
            "loop_id": 1, "search_query": "", "sources": [], "platforms": [],
            "channels": ["linkedin"], "min_score_threshold": 60,
            "max_applications_per_run": 5, "last_run_at": None, "schedule_interval_hours": 6,
        })
        monkeypatch.setattr("job_assistant.services.loops.get_loop_daily_usage", lambda *a, **kw: 0)
        monkeypatch.setattr("job_assistant.services.loops.execute_auto_apply_pipeline",
                           _raise(ValueError("Something broke")))
        monkeypatch.setattr("job_assistant.services.loops.create_loop_run", lambda *a, **kw: 100)
        monkeypatch.setattr("job_assistant.services.loops.update_loop_run", lambda *a, **kw: None)

        result = execute_loop(1, 1)
        assert result["status"] == "failed"
        assert "Something broke" in result["error"]


class TestCheckAndRunDueLoops:
    def test_no_active_loops(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_active_loops", lambda *a, **kw: [])
        results = check_and_run_due_loops(1)
        assert results == []

    def test_skips_loop_within_interval(self, monkeypatch):
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        monkeypatch.setattr("job_assistant.services.loops.get_active_loops", lambda *a, **kw: [
            {"loop_id": 1, "last_run_at": recent, "schedule_interval_hours": 6},
        ])
        monkeypatch.setattr("job_assistant.services.loops.execute_loop", lambda *a, **kw: None)
        results = check_and_run_due_loops(1)
        assert len(results) == 0

    def test_runs_loop_past_interval(self, monkeypatch):
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        monkeypatch.setattr("job_assistant.services.loops.get_active_loops", lambda *a, **kw: [
            {"loop_id": 1, "last_run_at": old, "schedule_interval_hours": 6},
        ])
        monkeypatch.setattr("job_assistant.services.loops.execute_loop",
                           lambda *a, **kw: {"loop_id": 1, "status": "completed"})
        results = check_and_run_due_loops(1)
        assert len(results) == 1
        assert results[0]["status"] == "completed"

    def test_handles_loop_execution_error(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_active_loops", lambda *a, **kw: [
            {"loop_id": 1, "last_run_at": None, "schedule_interval_hours": 6},
        ])
        monkeypatch.setattr("job_assistant.services.loops.execute_loop",
                           _raise(RuntimeError("Kaboom")))
        results = check_and_run_due_loops(1)
        assert len(results) == 1
        assert results[0]["status"] == "error"

    def test_loop_without_last_run_is_due(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_active_loops", lambda *a, **kw: [
            {"loop_id": 2, "last_run_at": None, "schedule_interval_hours": 6},
        ])
        monkeypatch.setattr("job_assistant.services.loops.execute_loop",
                           lambda *a, **kw: {"loop_id": 2, "status": "completed"})
        results = check_and_run_due_loops(1)
        assert len(results) == 1


class TestGetLoopStatus:
    def test_returns_status_with_budget(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_loop", lambda *a, **kw: {
            "loop_id": 1, "daily_budget": 20, "name": "Test",
        })
        monkeypatch.setattr("job_assistant.services.loops.get_loop_daily_usage", lambda *a, **kw: 5)
        monkeypatch.setattr("job_assistant.services.loops.list_loop_runs", lambda *a, **kw: [])
        status = get_loop_status(1, 1)
        assert status["daily_usage"] == 5
        assert status["budget_remaining"] == 15

    def test_raises_on_missing_loop(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.loops.get_loop", lambda *a, **kw: None)
        with pytest.raises(ValueError, match="not found"):
            get_loop_status(999, 1)


# ── Tests: services.auto_apply_pipeline ─────────────────────────────────────

class TestClassifyChannel:
    def test_linkedin_url_uses_linkedin_channel(self):
        job = {"url": "https://linkedin.com/jobs/view/123"}
        assert _classify_channel(job, ["linkedin_easy_apply", "email"]) == "linkedin_easy_apply"

    def test_non_linkedin_with_recruiter_email(self):
        job = {"url": "https://company.com/careers", "recruiter_email": "hr@company.com"}
        assert _classify_channel(job, ["linkedin_easy_apply", "email"]) == "email"

    def test_fallback_to_first_available(self):
        job = {"url": "https://company.com/careers", "recruiter_email": ""}
        assert _classify_channel(job, ["email"]) == "email"
        assert _classify_channel(job, ["linkedin_easy_apply"]) == "linkedin_easy_apply"

    def test_prefers_linkedin_over_email(self):
        job = {"url": "https://linkedin.com/jobs/view/1", "recruiter_email": "hr@co.com"}
        assert _classify_channel(job, ["linkedin_easy_apply", "email"]) == "linkedin_easy_apply"

    def test_empty_channels_returns_email(self):
        job = {"url": "", "recruiter_email": ""}
        assert _classify_channel(job, []) == "email"


class TestDiscoverJobs:
    def test_discover_empty_sources(self, monkeypatch):
        result = _discover_jobs("engineer", [], 1)
        assert result == []

    def test_discover_public_api_sources(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.discover_public_opportunities",
                           lambda **kw: [{"title": "Engineer", "source": "RemoteJobs.org"}])
        result = _discover_jobs("engineer", ["RemoteJobs.org"], 1)
        assert len(result) == 1

    def test_discover_public_api_failure(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.discover_public_opportunities",
                           _raise(Exception("API down")))
        result = _discover_jobs("engineer", ["RemoteJobs.org"], 1)
        assert result == []


class TestExecutePipeline:
    def test_pipeline_no_profile(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: None)
        result = execute_auto_apply_pipeline(1)
        assert result["status"] == "error"
        assert "No profile" in result["message"]

    def test_pipeline_empty_discovery(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test", "skills": "Python"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs",
                           lambda *a, **kw: [])
        result = execute_auto_apply_pipeline(1, query="engineer", sources=["RemoteJobs.org"])
        assert result["jobs_discovered"] == 0

    def test_pipeline_skips_low_score(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs",
                           lambda *a, **kw: [{"title": "Engineer", "company": "Co", "url": ""}])
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 30})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)

        result = execute_auto_apply_pipeline(1, min_score=60, max_applications=10)
        assert result["jobs_discovered"] == 1
        assert result["jobs_qualified"] == 0
        assert result["applications_attempted"] == 0

    def test_pipeline_dry_run_linkedin(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs",
                           lambda *a, **kw: [{"title": "Engineer", "company": "Co",
                                              "url": "https://linkedin.com/jobs/view/1"}])
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 85})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)
        async def mock_easy_apply(*a, **kw):
            return {"status": "dry_run"}
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.easy_apply_for_job",
                           mock_easy_apply)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.create_auto_apply_log",
                           lambda *a, **kw: 201)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.update_auto_apply_log",
                           lambda *a, **kw: None)

        result = execute_auto_apply_pipeline(1, channels=["linkedin_easy_apply"],
                                              min_score=50, max_applications=5)
        assert result["applications_submitted"] == 1
        assert result["budget_consumed"] == 1

    def test_pipeline_respects_max_applications(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs",
                           lambda *a, **kw: [
                               {"title": f"Engineer {i}", "company": "Co",
                                "url": f"https://linkedin.com/jobs/{i}"}
                               for i in range(10)
                           ])
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 90})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)
        async def mock_easy_apply(*a, **kw):
            return {"status": "dry_run"}
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.easy_apply_for_job",
                           mock_easy_apply)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.create_auto_apply_log",
                           lambda *a, **kw: 201)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.update_auto_apply_log",
                           lambda *a, **kw: None)

        result = execute_auto_apply_pipeline(1, channels=["linkedin_easy_apply"],
                                              min_score=50, max_applications=3)
        assert result["applications_submitted"] == 3

    def test_pipeline_handles_duplicate_job_gracefully(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs",
                           lambda *a, **kw: [{"title": "Engineer", "company": "Co", "url": ""}])
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           _raise(Exception("Duplicate")))
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 90})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)

        result = execute_auto_apply_pipeline(1, min_score=50)
        assert result["jobs_discovered"] == 1
        assert result["applications_attempted"] == 0  # duplicate skipped before apply


# ── Tests: Circuit breaker for multi-source discovery ───────────────────────

def _slow_fetcher(*, query: str = "", limit: int = 20) -> list:
    import time
    time.sleep(999)
    return []


def _failing_fetcher(*, query: str = "", limit: int = 20) -> list:
    raise ConnectionError("connection refused")


def _ok_fetcher(*, query: str = "", limit: int = 20) -> list:
    return [{"title": "Engineer", "company": "Co", "url": "https://example.com/job/1"}]


class TestCircuitBreaker:
    def test_allows_initial_request(self):
        from job_assistant.services.multi_source_discovery import circuit_breaker
        assert circuit_breaker.allow("TestSource") is True

    def test_opens_after_max_failures(self):
        from job_assistant.services.multi_source_discovery import circuit_breaker
        circuit_breaker.reset("TestFail")
        for i in range(3):
            circuit_breaker.record_failure("TestFail", f"error {i}")
        assert circuit_breaker.allow("TestFail") is False

    def test_records_success_resets_failures(self):
        from job_assistant.services.multi_source_discovery import circuit_breaker
        circuit_breaker.reset("TestReset")
        circuit_breaker.record_failure("TestReset", "error")
        circuit_breaker.record_failure("TestReset", "error")
        circuit_breaker.record_success("TestReset")
        assert circuit_breaker.allow("TestReset") is True

    def test_stats_returns_state(self):
        from job_assistant.services.multi_source_discovery import circuit_breaker
        circuit_breaker.reset("TestStats")
        stats = circuit_breaker.stats("TestStats")
        assert stats["source"] == "TestStats"
        assert stats["consecutive_failures"] == 0
        assert stats["circuit_open"] is False
        assert stats["last_error"] == ""

    def test_stats_shows_open_circuit(self):
        from job_assistant.services.multi_source_discovery import circuit_breaker
        circuit_breaker.reset("TestOpen")
        for _ in range(3):
            circuit_breaker.record_failure("TestOpen", "err")
        stats = circuit_breaker.stats("TestOpen")
        assert stats["circuit_open"] is True
        assert stats["consecutive_failures"] == 3

    def test_reset_clears_state(self):
        from job_assistant.services.multi_source_discovery import circuit_breaker
        for _ in range(3):
            circuit_breaker.record_failure("TestClear", "err")
        assert circuit_breaker.allow("TestClear") is False
        circuit_breaker.reset("TestClear")
        assert circuit_breaker.allow("TestClear") is True

    def test_circuit_breaker_ends_cooldown_after_record_success(self):
        from job_assistant.services.multi_source_discovery import circuit_breaker
        circuit_breaker.reset("TestCooldown")
        for _ in range(3):
            circuit_breaker.record_failure("TestCooldown", "err")
        assert circuit_breaker.allow("TestCooldown") is False
        circuit_breaker.record_success("TestCooldown")
        assert circuit_breaker.allow("TestCooldown") is True

    def test_fetch_source_with_timeout_success(self, monkeypatch):
        from job_assistant.services.multi_source_discovery import _fetch_source_with_timeout, circuit_breaker
        circuit_breaker.reset("TimeoutOK")
        items = _fetch_source_with_timeout("TimeoutOK", _ok_fetcher, "engineer", 5)
        assert len(items) == 1
        st = circuit_breaker.stats("TimeoutOK")
        assert st["consecutive_failures"] == 0

    def test_fetch_source_with_timeout_failure(self, monkeypatch):
        from job_assistant.services.multi_source_discovery import _fetch_source_with_timeout, circuit_breaker
        circuit_breaker.reset("TimeoutFail")
        items = _fetch_source_with_timeout("TimeoutFail", _failing_fetcher, "engineer", 5)
        assert items == []
        st = circuit_breaker.stats("TimeoutFail")
        assert st["consecutive_failures"] == 1

    def test_fetch_source_respects_open_circuit(self, monkeypatch):
        from job_assistant.services.multi_source_discovery import _fetch_source_with_timeout, circuit_breaker
        circuit_breaker.reset("CircuitOpen")
        for _ in range(3):
            circuit_breaker.record_failure("CircuitOpen", "err")
        items = _fetch_source_with_timeout("CircuitOpen", _ok_fetcher, "engineer", 5)
        assert items == []  # skipped because circuit is open

    def test_get_circuit_breaker_stats_returns_all_sources(self):
        from job_assistant.services.multi_source_discovery import get_circuit_breaker_stats
        stats = get_circuit_breaker_stats()
        source_names = {s["source"] for s in stats}
        assert "USAJobs" in source_names
        assert "CareerPage" in source_names

    def test_reset_all_circuit_breakers(self):
        from job_assistant.services.multi_source_discovery import get_circuit_breaker_stats, reset_circuit_breaker
        reset_circuit_breaker()
        stats = get_circuit_breaker_stats()
        for s in stats:
            assert s["consecutive_failures"] == 0
            assert s["circuit_open"] is False


# ── Tests: Auto-apply health endpoint ────────────────────────────────────


class TestAutoApplyHealthEndpoint:
    def _setup(self):
        from api_server import create_app
        from fastapi.testclient import TestClient
        from job_assistant.auth import current_user
        app = create_app()
        app.dependency_overrides[current_user] = lambda: {"id": 1}
        client = TestClient(app)
        return app, client

    def test_health_endpoint_returns_structure(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        app, client = self._setup()
        with patch("job_assistant.routes.loops.list_loops", return_value=[]):
            with patch("job_assistant.routes.loops.list_loop_runs", return_value=[]):
                with patch("job_assistant.routes.loops.get_loop_daily_usage", return_value=0):
                    with patch("job_assistant.routes.loops.get_auto_apply_stats", return_value={}):
                        with patch("job_assistant.routes.loops.get_daily_apply_count", return_value=0):
                            response = client.get("/api/v1/auto-apply/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "circuit_breaker" in data
        assert "loops" in data
        assert "runs" in data
        assert "auto_apply" in data

    def test_health_shows_inactive_with_no_runs(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        app, client = self._setup()
        with patch("job_assistant.routes.loops.list_loops", return_value=[]):
            with patch("job_assistant.routes.loops.list_loop_runs", return_value=[]):
                with patch("job_assistant.routes.loops.get_loop_daily_usage", return_value=0):
                    with patch("job_assistant.routes.loops.get_auto_apply_stats", return_value={}):
                        with patch("job_assistant.routes.loops.get_daily_apply_count", return_value=0):
                            response = client.get("/api/v1/auto-apply/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inactive"
        assert data["runs"]["total_last_7d"] == 0

    def test_health_shows_budget_exhaustion(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        app, client = self._setup()
        with patch("job_assistant.routes.loops.list_loops", return_value=[{"loop_id": 1, "is_active": True, "daily_budget": 5}]):
            with patch("job_assistant.routes.loops.list_loop_runs", return_value=[]):
                with patch("job_assistant.routes.loops.get_loop_daily_usage", return_value=5):
                    with patch("job_assistant.routes.loops.get_auto_apply_stats", return_value={}):
                        with patch("job_assistant.routes.loops.get_daily_apply_count", return_value=0):
                            response = client.get("/api/v1/auto-apply/health")
        assert response.status_code == 200
        data = response.json()
        assert data["loops"]["today_usage"] == 5
        assert data["loops"]["budget_remaining"] == 0

    def test_reset_circuit_breaker_endpoint(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        app, client = self._setup()
        with patch("job_assistant.routes.loops.reset_circuit_breaker") as m:
            m.return_value = None
            response = client.post("/api/v1/auto-apply/health/reset-circuit-breaker",
                                    headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_reset_circuit_breaker_with_source(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        app, client = self._setup()
        with patch("job_assistant.routes.loops.reset_circuit_breaker") as m:
            m.return_value = None
            response = client.post("/api/v1/auto-apply/health/reset-circuit-breaker?source=USAJobs",
                                    headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ── Full pipeline end-to-end with mocked LinkedIn Easy Apply ─────────────


class TestPipelineEndToEnd:
    """End-to-end pipeline tests simulating the full discover→score→apply flow."""

    def test_pipeline_processes_linkedin_and_email_jobs(self, monkeypatch):
        mock_jobs = [
            {"title": "Engineer A", "company": "Co A", "url": "https://linkedin.com/jobs/view/1"},
            {"title": "Engineer B", "company": "Co B", "url": "https://company.com/careers",
             "recruiter_email": "hr@co.com"},
        ]
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs", lambda *a, **kw: mock_jobs)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test", "skills": "Python"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 85})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._apply_via_linkedin",
                           lambda *a, **kw: {"status": "submitted"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._apply_via_email",
                           lambda *a, **kw: {"status": "submitted"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.create_auto_apply_log",
                           lambda *a, **kw: 201)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.update_auto_apply_log",
                           lambda *a, **kw: None)

        result = execute_auto_apply_pipeline(
            1, channels=["linkedin_easy_apply", "email"],
            min_score=50, max_applications=10,
        )
        assert result["status"] == "completed"
        assert result["jobs_discovered"] == 2
        assert result["jobs_qualified"] == 2
        assert result["applications_submitted"] == 2
        assert result["budget_consumed"] == 2

    def test_pipeline_stops_at_max_applications(self, monkeypatch):
        mock_jobs = [
            {"title": f"Engineer {i}", "company": "Co", "url": f"https://linkedin.com/jobs/view/{i}"}
            for i in range(10)
        ]
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs", lambda *a, **kw: mock_jobs)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 90})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._apply_via_linkedin",
                           lambda *a, **kw: {"status": "submitted"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.create_auto_apply_log",
                           lambda *a, **kw: 201)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.update_auto_apply_log",
                           lambda *a, **kw: None)

        result = execute_auto_apply_pipeline(1, channels=["linkedin_easy_apply"],
                                               min_score=50, max_applications=3)
        assert result["applications_submitted"] == 3
        assert result["budget_consumed"] == 3

    def test_pipeline_handles_mixed_channel_results(self, monkeypatch):
        mock_jobs = [
            {"title": "Job A", "company": "Co", "url": "https://linkedin.com/jobs/view/1"},
            {"title": "Job B", "company": "Co", "url": "https://company.com/apply",
             "recruiter_email": "hr@co.com"},
        ]
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs", lambda *a, **kw: mock_jobs)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test", "skills": "Python",
                                              "user_id": 1})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 80})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.create_auto_apply_log",
                           lambda *a, **kw: 201)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.update_auto_apply_log",
                           lambda *a, **kw: None)

        apply_results = iter([{"status": "submitted"}, {"status": "failed", "reason": "Net error"}])

        def mock_apply_via_linkedin(job=None, user_id=0, dry_run=True):
            return next(apply_results)

        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._apply_via_linkedin",
                           mock_apply_via_linkedin)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._apply_via_email",
                           lambda *a, **kw: {"status": "submitted"})

        result = execute_auto_apply_pipeline(1, channels=["linkedin_easy_apply", "email"],
                                               min_score=50, max_applications=10)
        assert result["jobs_discovered"] == 2
        assert result["applications_attempted"] == 2
        assert result["applications_submitted"] >= 1
        assert result["applications_failed"] >= 0

    def test_pipeline_with_dry_run_counts_as_submitted(self, monkeypatch):
        mock_jobs = [
            {"title": "Engineer", "company": "Co", "url": "https://linkedin.com/jobs/view/1"},
        ]
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs", lambda *a, **kw: mock_jobs)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 85})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._apply_via_linkedin",
                           lambda *a, **kw: {"status": "dry_run"})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.create_auto_apply_log",
                           lambda *a, **kw: 201)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.update_auto_apply_log",
                           lambda *a, **kw: None)

        result = execute_auto_apply_pipeline(1, channels=["linkedin_easy_apply"],
                                               min_score=50, max_applications=5, dry_run=True)
        assert result["applications_submitted"] == 1
        assert result["budget_consumed"] == 1

    def test_pipeline_empty_discovery_returns_early(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs", lambda *a, **kw: [])
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        result = execute_auto_apply_pipeline(1, query="engineer", sources=["RemoteJobs.org"])
        assert result["jobs_discovered"] == 0
        assert result["applications_attempted"] == 0

    def test_pipeline_handles_discovery_error(self, monkeypatch):
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs",
                           _raise(Exception("Discovery failed")))
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test"})
        with pytest.raises(Exception, match="Discovery failed"):
            execute_auto_apply_pipeline(1)

    def test_pipeline_with_no_valid_channels_falls_back(self, monkeypatch):
        mock_jobs = [
            {"title": "Engineer", "company": "Co", "url": "https://linkedin.com/jobs/view/1"},
        ]
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._discover_jobs", lambda *a, **kw: mock_jobs)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.get_profile",
                           lambda *a, **kw: {"full_name": "Test", "user_id": 1})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.insert_job",
                           lambda *a, **kw: 101)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.score_job",
                           lambda *a, **kw: {"match_score": 70})
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.save_evaluation",
                           lambda *a, **kw: None)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.create_auto_apply_log",
                           lambda *a, **kw: 201)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline.update_auto_apply_log",
                           lambda *a, **kw: None)
        monkeypatch.setattr("job_assistant.services.auto_apply_pipeline._apply_via_linkedin",
                           lambda *a, **kw: {"status": "submitted"})

        result = execute_auto_apply_pipeline(1, channels=[], min_score=50)
        assert result["status"] == "completed"
        assert result["jobs_qualified"] == 1
        assert result["applications_attempted"] == 1  # falls back to first channel
