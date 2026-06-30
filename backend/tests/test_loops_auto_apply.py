from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from job_assistant.db.loops import (
    create_loop, get_loop, list_loops, update_loop, delete_loop,
    create_loop_run, update_loop_run, list_loop_runs,
    get_loop_daily_usage, get_active_loops,
)
from job_assistant.db.auto_apply import (
    create_auto_apply_log, update_auto_apply_log, get_auto_apply_log,
    list_auto_apply_logs, get_auto_apply_stats, get_daily_apply_count,
    get_pending_approval_logs,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db(monkeypatch):
    """Replace get_collection with a pre-seeded dict of MagicMock collections."""
    collections = {
        "loops": MagicMock(),
        "loop_runs": MagicMock(),
        "auto_apply_logs": MagicMock(),
        "counters": MagicMock(),
        "audit_logs": MagicMock(),
    }

    def fake_get_collection(name: str) -> MagicMock:
        return collections[name]

    monkeypatch.setattr("job_assistant.db.loops.get_collection", fake_get_collection)
    monkeypatch.setattr("job_assistant.db.auto_apply.get_collection", fake_get_collection)
    monkeypatch.setattr("job_assistant.db.loops._workspace_scope_for_user", lambda uid, wid: (wid or 1, 1))
    monkeypatch.setattr("job_assistant.db.auto_apply._workspace_scope_for_user", lambda uid, wid: (wid or 1, 1))
    return collections


@pytest.fixture
def mock_utcnow(monkeypatch):
    fake_now = "2026-06-30T12:00:00"
    monkeypatch.setattr("job_assistant.db.loops.utc_now", lambda: fake_now)
    monkeypatch.setattr("job_assistant.db.auto_apply.utc_now", lambda: fake_now)
    return fake_now


def _install_next_id(monkeypatch):
    counters: dict[str, int] = {}
    def fake_next_id(seq: str) -> int:
        counters[seq] = counters.get(seq, 0) + 1
        return counters[seq]
    monkeypatch.setattr("job_assistant.db.loops._next_id", fake_next_id)
    monkeypatch.setattr("job_assistant.db.auto_apply._next_id", fake_next_id)
    return counters


# ── Tests: db.loops ─────────────────────────────────────────────────────────

class TestLoopsDB:
    def test_create_loop_minimal(self, mock_db, mock_utcnow):
        lid = create_loop(1, {"name": "Test Loop", "search_query": "engineer"})
        assert lid > 0
        doc = mock_db["loops"].insert_one.call_args[0][0]
        assert doc["loop_id"] == lid
        assert doc["name"] == "Test Loop"
        assert doc["search_query"] == "engineer"
        assert doc["daily_budget"] == 10
        assert doc["auto_apply_enabled"] == 0

    def test_create_loop_full(self, mock_db, mock_utcnow):
        lid = create_loop(1, {
            "name": "Senior Roles",
            "search_query": "senior engineer react",
            "sources": ["LinkedIn", "RemoteJobs.org"],
            "platforms": ["linkedin", "email"],
            "is_active": True,
            "auto_apply_enabled": True,
            "daily_budget": 25,
            "max_applications_per_run": 10,
            "min_score_threshold": 75,
            "channels": ["linkedin", "email"],
            "schedule_interval_hours": 12,
        })
        doc = mock_db["loops"].insert_one.call_args[0][0]
        assert doc["daily_budget"] == 25
        assert doc["max_applications_per_run"] == 10
        assert doc["min_score_threshold"] == 75
        assert doc["auto_apply_enabled"] == 1
        assert doc["channels"] == ["linkedin", "email"]
        assert doc["schedule_interval_hours"] == 12

    def test_get_loop_returns_none_when_missing(self, mock_db):
        mock_db["loops"].find_one.return_value = None
        result = get_loop(999, 1)
        assert result is None

    def test_list_loops_active_only(self, mock_db):
        from unittest.mock import MagicMock
        sort_mock = MagicMock()
        sort_mock.__iter__.return_value = iter([
            {"loop_id": 1, "is_active": 1},
            {"loop_id": 2, "is_active": 1},
        ])
        mock_db["loops"].find.return_value.sort.return_value = sort_mock
        results = list_loops(1)
        assert len(results) == 2
        assert mock_db["loops"].find.call_args[0][0].get("is_active") == 1

    def test_list_loops_include_inactive(self, mock_db):
        from unittest.mock import MagicMock
        sort_mock = MagicMock()
        sort_mock.__iter__.return_value = iter([
            {"loop_id": 1, "is_active": 0},
            {"loop_id": 2, "is_active": 1},
        ])
        mock_db["loops"].find.return_value.sort.return_value = sort_mock
        results = list_loops(1, include_inactive=True)
        assert len(results) == 2
        assert "is_active" not in mock_db["loops"].find.call_args[0][0]

    def test_update_loop_raises_on_missing(self, mock_db):
        mock_db["loops"].find_one.return_value = None
        with pytest.raises(ValueError, match="Loop not found"):
            update_loop(999, 1, {"name": "Nope"})

    def test_update_loop_partial(self, mock_db):
        mock_db["loops"].find_one.return_value = {
            "loop_id": 1, "user_id": 1, "workspace_id": 1, "organization_id": 1,
            "name": "Old", "daily_budget": 10, "is_active": 1, "auto_apply_enabled": 0,
        }
        update_loop(1, 1, {"name": "New Name", "daily_budget": 20})
        update_call = mock_db["loops"].update_one.call_args
        assert update_call[0][0] == {"loop_id": 1, "user_id": 1, "workspace_id": 1}
        assert update_call[0][1]["$set"]["name"] == "New Name"
        assert update_call[0][1]["$set"]["daily_budget"] == 20

    def test_delete_loop_removes_runs(self, mock_db):
        mock_db["loops"].find_one.return_value = {"loop_id": 1, "user_id": 1, "workspace_id": 1, "organization_id": 1}
        delete_loop(1, 1)
        mock_db["loops"].delete_one.assert_called_once()
        mock_db["loop_runs"].delete_many.assert_called_once_with(
            {"loop_id": 1, "user_id": 1, "workspace_id": 1}
        )

    def test_create_loop_run(self, mock_db, mock_utcnow):
        rid = create_loop_run(1, 1)
        assert rid > 0
        doc = mock_db["loop_runs"].insert_one.call_args[0][0]
        assert doc["loop_id"] == 1
        assert doc["status"] == "running"

    def test_update_loop_run(self, mock_db):
        update_loop_run(1, 1, status="completed", applications_sent=5, budget_consumed=3)
        update = mock_db["loop_runs"].update_one.call_args[0][1]["$set"]
        assert update["status"] == "completed"
        assert update["applications_sent"] == 5
        assert update["budget_consumed"] == 3

    def test_get_loop_daily_usage(self, mock_db):
        mock_db["loop_runs"].aggregate.return_value = [{"total": 7}]
        usage = get_loop_daily_usage(1, 1)
        assert usage == 7

    def test_get_loop_daily_usage_empty(self, mock_db):
        mock_db["loop_runs"].aggregate.return_value = []
        usage = get_loop_daily_usage(1, 1)
        assert usage == 0

    def test_get_active_loops(self, mock_db):
        mock_db["loops"].find.return_value = [
            {"loop_id": 1, "is_active": 1, "auto_apply_enabled": 1},
        ]
        results = get_active_loops(1)
        assert len(results) == 1
        query = mock_db["loops"].find.call_args[0][0]
        assert query["is_active"] == 1
        assert query["auto_apply_enabled"] == 1

    def test_loop_budget_clamping(self, mock_db, mock_utcnow):
        create_loop(1, {"daily_budget": -5, "min_score_threshold": 150, "max_applications_per_run": 0})
        doc = mock_db["loops"].insert_one.call_args[0][0]
        assert doc["daily_budget"] == 0
        assert doc["min_score_threshold"] == 100
        assert doc["max_applications_per_run"] == 1

    def test_channels_normalization(self, mock_db, mock_utcnow):
        create_loop(1, {"channels": ["linkedin", "email", "invalid_channel", "ats_form"]})
        doc = mock_db["loops"].insert_one.call_args[0][0]
        assert doc["channels"] == ["linkedin", "email", "ats_form"]


# ── Tests: db.auto_apply ────────────────────────────────────────────────────

class TestAutoApplyDB:
    def test_create_log_minimal(self, mock_db, mock_utcnow):
        log_id = create_auto_apply_log(1, 101, "linkedin_easy_apply")
        assert log_id > 0
        doc = mock_db["auto_apply_logs"].insert_one.call_args[0][0]
        assert doc["job_id"] == 101
        assert doc["channel"] == "linkedin_easy_apply"
        assert doc["status"] == "pending"

    def test_create_log_with_loop_context(self, mock_db, mock_utcnow):
        create_auto_apply_log(1, 101, "email", loop_id=5, run_id=10, score=85)
        doc = mock_db["auto_apply_logs"].insert_one.call_args[0][0]
        assert doc["loop_id"] == 5
        assert doc["run_id"] == 10
        assert doc["score"] == 85

    def test_create_log_invalid_channel_falls_back(self, mock_db, mock_utcnow):
        create_auto_apply_log(1, 101, "fax_machine")
        doc = mock_db["auto_apply_logs"].insert_one.call_args[0][0]
        assert doc["channel"] == "email"

    def test_create_log_with_workspace(self, mock_db, mock_utcnow):
        create_auto_apply_log(1, 101, "linkedin_easy_apply", workspace_id=42)
        doc = mock_db["auto_apply_logs"].insert_one.call_args[0][0]
        assert doc["workspace_id"] == 42

    def test_update_log_status(self, mock_db):
        update_auto_apply_log(1, 1, status="submitted")
        update = mock_db["auto_apply_logs"].update_one.call_args[0][1]["$set"]
        assert update["status"] == "submitted"

    def test_update_log_with_error(self, mock_db):
        update_auto_apply_log(1, 1, status="failed", error_message="Connection timeout")
        update = mock_db["auto_apply_logs"].update_one.call_args[0][1]["$set"]
        assert update["error_message"] == "Connection timeout"

    def test_update_log_with_details(self, mock_db):
        update_auto_apply_log(1, 1, status="submitted", details={"url": "https://linkedin.com/jobs/123", "dry_run": True})
        update = mock_db["auto_apply_logs"].update_one.call_args[0][1]["$set"]
        details = json.loads(update["details_json"])
        assert details["url"] == "https://linkedin.com/jobs/123"
        assert details["dry_run"] is True

    def test_update_log_invalid_status_coerced(self, mock_db):
        update_auto_apply_log(1, 1, status="nonsense")
        update = mock_db["auto_apply_logs"].update_one.call_args[0][1]["$set"]
        assert update["status"] == "failed"

    def test_get_log_returns_none_when_missing(self, mock_db):
        mock_db["auto_apply_logs"].find_one.return_value = None
        assert get_auto_apply_log(999, 1) is None

    def test_get_log_formatted(self, mock_db):
        mock_db["auto_apply_logs"].find_one.return_value = {
            "auto_apply_log_id": 1, "job_id": 101, "details_json": '{"dry_run": true}',
        }
        result = get_auto_apply_log(1, 1)
        assert result["details"] == {"dry_run": True}

    def test_list_logs_filters_by_status(self, mock_db):
        from unittest.mock import MagicMock
        sort_mock = MagicMock()
        sort_mock.limit.return_value = []
        mock_db["auto_apply_logs"].find.return_value.sort.return_value = sort_mock
        list_auto_apply_logs(1, status="failed")
        query = mock_db["auto_apply_logs"].find.call_args[0][0]
        assert query["status"] == "failed"

    def test_list_logs_filters_by_loop(self, mock_db):
        from unittest.mock import MagicMock
        sort_mock = MagicMock()
        sort_mock.limit.return_value = []
        mock_db["auto_apply_logs"].find.return_value.sort.return_value = sort_mock
        list_auto_apply_logs(1, loop_id=7)
        query = mock_db["auto_apply_logs"].find.call_args[0][0]
        assert query["loop_id"] == 7

    def test_stats_aggregation(self, mock_db):
        mock_db["auto_apply_logs"].aggregate.return_value = [
            {"_id": "submitted", "count": 10},
            {"_id": "failed", "count": 2},
        ]
        stats = get_auto_apply_stats(1)
        assert stats["total"] == 12
        assert stats["submitted"] == 10
        assert stats["failed"] == 2

    def test_stats_empty(self, mock_db):
        mock_db["auto_apply_logs"].aggregate.return_value = []
        stats = get_auto_apply_stats(1)
        assert stats["total"] == 0

    def test_daily_apply_count(self, mock_db):
        mock_db["auto_apply_logs"].count_documents.return_value = 5
        assert get_daily_apply_count(1) == 5

    def test_pending_approval_returns_logs(self, mock_db):
        from unittest.mock import MagicMock
        sort_mock = MagicMock()
        sort_mock.limit.return_value = [
            {"auto_apply_log_id": 1, "details_json": "{}"},
        ]
        mock_db["auto_apply_logs"].find.return_value.sort.return_value = sort_mock
        results = get_pending_approval_logs(1)
        assert len(results) == 1
        query = mock_db["auto_apply_logs"].find.call_args[0][0]
        assert query["status"] == "needs_approval"
