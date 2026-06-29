from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from job_assistant.config import settings


# ── Freshness filter ────────────────────────────────────────────────────

class TestFreshnessFilter:
    def test_freshness_filter_passes_recent(self):
        from job_assistant.services.public_discovery import _freshness_filter
        from datetime import datetime, timedelta
        recent = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
        items = [{"title": "Job A", "date_received": recent}]
        result = _freshness_filter(items, max_age_days=30)
        assert len(result) == 1

    def test_freshness_filter_removes_stale(self):
        from job_assistant.services.public_discovery import _freshness_filter
        from datetime import datetime, timedelta
        stale = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d")
        items = [{"title": "Job A", "date_received": stale}]
        result = _freshness_filter(items, max_age_days=30)
        assert len(result) == 0

    def test_freshness_filter_passes_items_without_date(self):
        from job_assistant.services.public_discovery import _freshness_filter
        items = [{"title": "Job A", "date_received": ""}, {"title": "Job B"}]
        result = _freshness_filter(items, max_age_days=30)
        assert len(result) == 2

    def test_freshness_filter_none_max_age(self):
        from job_assistant.services.public_discovery import _freshness_filter
        items = [{"title": "Job A", "date_received": "2020-01-01"}]
        result = _freshness_filter(items, max_age_days=None)
        assert len(result) == 1

    def test_freshness_filter_zero_max_age(self):
        from job_assistant.services.public_discovery import _freshness_filter
        items = [{"title": "Job A", "date_received": "2020-01-01"}]
        result = _freshness_filter(items, max_age_days=0)
        assert len(result) == 1

    def test_freshness_filter_invalid_date_passes(self):
        from job_assistant.services.public_discovery import _freshness_filter
        items = [{"title": "Job A", "date_received": "not-a-date"}]
        result = _freshness_filter(items, max_age_days=30)
        assert len(result) == 1


# ── Security headers ────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_security_headers_present(self):
        with patch.object(settings, "security_headers_enabled", True):
            with patch.object(settings, "hsts_max_age", 31536000):
                with patch.object(settings, "content_security_policy", "default-src 'self'"):
                    from api_server import create_app
                    app = create_app()
                    client = TestClient(app)
                    with patch("job_assistant.auth.current_user") as mock_auth:
                        mock_auth.return_value = {"id": 1}
                        resp = client.get("/api/v1/health")
                        assert resp.headers.get("x-content-type-options") == "nosniff"
                        assert resp.headers.get("x-frame-options") == "DENY"
                        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
                        assert resp.headers.get("strict-transport-security", "").startswith("max-age=31536000")
                        assert resp.headers.get("content-security-policy") == "default-src 'self'"

    def test_security_headers_disabled(self):
        with patch.object(settings, "security_headers_enabled", False):
            from api_server import create_app
            app = create_app()
            client = TestClient(app)
            with patch("job_assistant.auth.current_user") as mock_auth:
                mock_auth.return_value = {"id": 1}
                resp = client.get("/api/v1/health")
                assert "x-content-type-options" not in resp.headers


# ── CSRF protection ─────────────────────────────────────────────────────

class TestCsrfProtection:
    def test_csrf_blocks_missing_origin_on_mutation(self):
        with patch.object(settings, "csrf_enabled", True):
            from api_server import create_app
            app = create_app()
            client = TestClient(app)
            resp = client.post("/api/v1/discovery/public", json={})
            assert resp.status_code == 403
            assert "CSRF" in resp.json()["detail"]

    def test_csrf_allows_valid_origin(self):
        with patch.object(settings, "csrf_enabled", True):
            from api_server import create_app
            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/api/v1/discovery/public",
                json={},
                headers={"Origin": "http://localhost:3000"},
            )
            assert resp.status_code != 403

    def test_csrf_allows_safe_methods(self):
        with patch.object(settings, "csrf_enabled", True):
            from api_server import create_app
            app = create_app()
            client = TestClient(app)
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200

    def test_csrf_exempt_paths(self):
        with patch.object(settings, "csrf_enabled", True):
            with patch.object(settings, "csrf_exempt_paths", "/api/v1/auth/login"):
                from api_server import create_app
                app = create_app()
                client = TestClient(app)
                resp = client.post("/api/v1/auth/login", json={})
                assert resp.status_code != 403


# ── Publishing engine ───────────────────────────────────────────────────

class TestPublishingEngine:
    def test_validate_target_ok(self):
        from job_assistant.publishing_engine import validate_target
        result = validate_target("linkedin", "Hello world", 0)
        assert result.ok
        assert not result.errors

    def test_validate_target_too_long(self):
        from job_assistant.publishing_engine import validate_target
        result = validate_target("x", "x" * 300, 0)
        assert not result.ok
        assert any("exceeds" in e for e in result.errors)

    def test_validate_target_empty(self):
        from job_assistant.publishing_engine import validate_target
        result = validate_target("linkedin", "", 0)
        assert not result.ok

    def test_publish_post_dry_run(self):
        from job_assistant.publishing_engine import publish_post
        with patch("job_assistant.publishing_engine.get_post") as mock_get:
            mock_get.return_value = {
                "post_id": 1,
                "status": "approved",
                "targets": [
                    {"id": 1, "platform": "linkedin", "transformed_content": "Test post"},
                ],
            }
            result = publish_post(1, 1, dry_run=True)
            assert result["dry_run"] is True

    def test_publish_post_live_calls_provider(self):
        from job_assistant.publishing_engine import publish_post
        with patch("job_assistant.publishing_engine.get_post") as mock_get:
            mock_get.return_value = {
                "post_id": 1,
                "status": "approved",
                "targets": [
                    {"id": 1, "platform": "linkedin", "transformed_content": "Test post"},
                ],
            }
            with patch("job_assistant.publishing_engine.provider_registry.execute_with_fallback") as mock_exec:
                mock_exec.return_value = type("Result", (), {"ok": True, "provider_name": "linkedin", "error": ""})()
                result = publish_post(1, 1, dry_run=False)
                assert result["dry_run"] is False
                assert mock_exec.called

    def test_linkedin_adapter_execute(self):
        from job_assistant.publishing_engine import LinkedInProvider
        adapter = LinkedInProvider(
            credentials={"api_key": "test-token"},
            config={"author_urn": "urn:li:person:123"},
        )
        with patch("job_assistant.services.linkedin_integration.publish_text_post") as mock_publish:
            mock_publish.return_value = {"post_id": "abc-123"}
            result = adapter.execute("publish_post", {"content": "Hello"})
            assert result["status"] == "published"
            assert result["post_id"] == "abc-123"

    def test_linkedin_adapter_missing_credentials(self):
        from job_assistant.publishing_engine import LinkedInProvider
        adapter = LinkedInProvider(credentials={}, config={"author_urn": "urn:li:person:123"})
        with pytest.raises(ValueError, match="API token"):
            adapter.execute("publish_post", {"content": "Hello"})

    def test_linkedin_adapter_missing_urn(self):
        from job_assistant.publishing_engine import LinkedInProvider
        adapter = LinkedInProvider(credentials={"api_key": "test"}, config={})
        with pytest.raises(ValueError, match="URN"):
            adapter.execute("publish_post", {"content": "Hello"})

    def test_approve_post(self):
        from job_assistant.publishing_engine import approve_post
        with patch("job_assistant.publishing_engine.get_collection") as mock_coll:
            mock_coll.return_value.find_one.return_value = {"_id": 1, "user_id": 1, "workspace_id": None, "organization_id": None}
            approve_post(1, 1)

    def test_post_lifecycle(self):
        from job_assistant.db.publishing import create_post, list_posts
        from job_assistant.publishing_engine import approve_post, publish_post
        with patch("job_assistant.db.publishing.get_collection") as mock_db:
            mock_coll = mock_db.return_value
            mock_coll.insert_one.return_value = None
            with patch("job_assistant.db.publishing._next_id") as mock_id:
                mock_id.return_value = 42
                with patch("job_assistant.db.publishing._workspace_scope_for_user") as mock_scope:
                    mock_scope.return_value = (None, None)
                    with patch("job_assistant.db.publishing.add_audit_log"):
                        post_id = create_post(1, {"base_content": "Test", "targets": [{"platform": "linkedin"}]})
                        assert post_id == 42


# ── Abbreviation expansion (enhanced fuzzy dedup) ──────────────────────

class TestAbbreviationExpansion:
    def test_new_abbreviations_expanded(self):
        from job_assistant.db.jobs import _normalize_for_fuzzy
        assert "softwareengineer" in _normalize_for_fuzzy("SWE")
        assert "softwaredevelopmentengineer" in _normalize_for_fuzzy("SDE")
        assert "frontend" in _normalize_for_fuzzy("FE")
        assert "backend" in _normalize_for_fuzzy("BE")
        assert "datascientist" in _normalize_for_fuzzy("DS")
        assert "productmanager" in _normalize_for_fuzzy("PM")
        assert "qualityassurance" in _normalize_for_fuzzy("QA")

    def test_case_insensitive_abbreviation(self):
        from job_assistant.db.jobs import _normalize_for_fuzzy
        assert _normalize_for_fuzzy("swe") == _normalize_for_fuzzy("SWE")
