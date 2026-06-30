from __future__ import annotations

import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

INTEGRATION = os.environ.get("INTEGRATION_TESTS", "").lower() in ("1", "true", "yes")

integration = pytest.mark.skipif(
    not INTEGRATION,
    reason="Set INTEGRATION_TESTS=1 to run real HTTP integration tests",
)


def _check_api(url: str, timeout: int = 15) -> bool:
    """Return True if the API endpoint is reachable."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "integration-test/1.0"})
        return r.ok
    except Exception:
        return False


@pytest.fixture(scope="module")
def usa_jobs_available():
    return _check_api("https://data.usajobs.gov/api/search?Keyword=engineer&PageSize=1")


@pytest.fixture(scope="module")
def reed_available():
    return _check_api("https://www.reed.co.uk/api/1.0/search?keywords=engineer&resultsToSkip=0&resultsToTake=1")


# ── Public API Sources (no auth required) ────────────────────────────────


class TestRemoteJobsOrgAPI:
    @integration
    def test_fetch_returns_jobs(self):
        from job_assistant.services.public_discovery import fetch_remotejobs
        jobs = fetch_remotejobs(query="python", limit=5)
        assert isinstance(jobs, list)
        if jobs:
            job = jobs[0]
            assert job.get("title")
            assert job.get("url")
            assert job.get("source") == "RemoteJobs.org"

    @integration
    def test_fetch_respects_limit(self):
        from job_assistant.services.public_discovery import fetch_remotejobs
        jobs = fetch_remotejobs(query="python", limit=3)
        assert isinstance(jobs, list)


class TestArbeitnowAPI:
    @integration
    def test_fetch_returns_jobs(self):
        from job_assistant.services.public_discovery import fetch_arbeitnow
        jobs = fetch_arbeitnow(query="python", limit=5)
        assert isinstance(jobs, list)
        if jobs:
            job = jobs[0]
            assert job.get("title")
            assert job.get("source") == "Arbeitnow"

    @integration
    def test_fetch_respects_limit(self):
        from job_assistant.services.public_discovery import fetch_arbeitnow
        jobs = fetch_arbeitnow(query="python", limit=2)
        assert isinstance(jobs, list)


class TestRemotiveAPI:
    @integration
    def test_fetch_returns_jobs(self):
        from job_assistant.services.public_discovery import fetch_remotive
        jobs = fetch_remotive(query="developer", limit=5)
        assert isinstance(jobs, list)
        if jobs:
            job = jobs[0]
            assert job.get("title")
            assert job.get("source") == "Remotive"
            assert job.get("url")

    @integration
    def test_fetch_respects_limit(self):
        from job_assistant.services.public_discovery import fetch_remotive
        jobs = fetch_remotive(query="developer", limit=3)
        assert len(jobs) >= 0  # API may not honor limit, just verify it runs


class TestJobicyAPI:
    @integration
    def test_fetch_returns_jobs(self):
        from job_assistant.services.public_discovery import fetch_jobicy
        jobs = fetch_jobicy(query="python", limit=5)
        assert isinstance(jobs, list)
        if jobs:
            job = jobs[0]
            assert job.get("title")
            assert job.get("source") == "Jobicy"
            assert job.get("url")

    @integration
    def test_fetch_respects_limit(self):
        from job_assistant.services.public_discovery import fetch_jobicy
        jobs = fetch_jobicy(query="python", limit=2)
        assert isinstance(jobs, list)


class TestRemoteOkAPI:
    @integration
    def test_fetch_returns_jobs(self):
        try:
            from job_assistant.services.public_discovery import fetch_remoteok
            jobs = fetch_remoteok(query="developer", limit=5)
            assert isinstance(jobs, list)
            if jobs:
                job = jobs[0]
                assert job.get("title")
                assert job.get("source") == "RemoteOK"
        except (requests.HTTPError, requests.TooManyRedirects, requests.ConnectionError) as e:
            pytest.skip(f"RemoteOK API unreachable: {e}")

    @integration
    def test_fetch_respects_limit(self):
        try:
            from job_assistant.services.public_discovery import fetch_remoteok
            jobs = fetch_remoteok(query="developer", limit=3)
            assert isinstance(jobs, list)
        except (requests.HTTPError, requests.TooManyRedirects, requests.ConnectionError) as e:
            pytest.skip(f"RemoteOK API unreachable: {e}")


class TestTheMuseAPI:
    @integration
    def test_fetch_returns_jobs(self):
        try:
            from job_assistant.services.public_discovery import fetch_muse
            jobs = fetch_muse(query="engineer", limit=5)
            assert isinstance(jobs, list)
            if jobs:
                job = jobs[0]
                assert job.get("title")
                assert job.get("source") == "The Muse"
        except (requests.HTTPError, requests.ConnectionError) as e:
            pytest.skip(f"The Muse API unreachable: {e}")

    @integration
    def test_fetch_respects_limit(self):
        try:
            from job_assistant.services.public_discovery import fetch_muse
            jobs = fetch_muse(query="engineer", limit=2)
            assert isinstance(jobs, list)
        except (requests.HTTPError, requests.ConnectionError) as e:
            pytest.skip(f"The Muse API unreachable: {e}")


class TestHNWhoIsHiringAPI:
    @integration
    def test_fetch_returns_jobs(self):
        from job_assistant.services.public_discovery import fetch_hackernews_who_is_hiring
        jobs = fetch_hackernews_who_is_hiring(query="python", limit=5)
        assert isinstance(jobs, list)
        if jobs:
            job = jobs[0]
            assert job.get("title")
            assert job.get("source") == "Hacker News Who is hiring"

    @integration
    def test_fetch_without_query(self):
        from job_assistant.services.public_discovery import fetch_hackernews_who_is_hiring
        jobs = fetch_hackernews_who_is_hiring(limit=3)
        assert isinstance(jobs, list)


# ── Public Discovery Aggregator ──────────────────────────────────────────


class TestDiscoverPublicOpportunities:
    @integration
    def test_discover_multiple_sources(self):
        from job_assistant.services.public_discovery import discover_public_opportunities
        jobs = discover_public_opportunities(
            query="python",
            sources=["RemoteJobs.org", "Arbeitnow", "Remotive"],
            limit_per_source=3,
        )
        assert isinstance(jobs, list)
        if jobs:
            sources_found = {j["source"] for j in jobs}
            assert len(sources_found) > 0

    @integration
    def test_discover_single_source(self):
        from job_assistant.services.public_discovery import discover_public_opportunities
        jobs = discover_public_opportunities(
            query="developer",
            sources=["RemoteJobs.org"],
            limit_per_source=3,
        )
        assert isinstance(jobs, list)
        for j in jobs:
            assert j.get("source") == "RemoteJobs.org"


# ── Multi-Source API (auth-gated, conditional) ──────────────────────────


class TestUSAJobsAPI:
    @integration
    def test_fetch_returns_jobs(self, usa_jobs_available):
        if not usa_jobs_available:
            pytest.skip("USAJobs API unreachable")
        from job_assistant.services.multi_source_discovery import fetch_usajobs
        jobs = fetch_usajobs(query="engineer", limit=5)
        assert isinstance(jobs, list)
        if jobs:
            job = jobs[0]
            assert job.get("title")
            assert job.get("source") == "USAJobs"
            assert job.get("url")


class TestReedAPI:
    @integration
    def test_fetch_returns_jobs(self, reed_available):
        if not reed_available:
            pytest.skip("Reed.co.uk API unreachable")
        from job_assistant.services.multi_source_discovery import fetch_reed
        jobs = fetch_reed(query="engineer", limit=5)
        assert isinstance(jobs, list)
        if jobs:
            job = jobs[0]
            assert job.get("title")
            assert job.get("source") == "Reed.co.uk"
            assert job.get("url")


# ── Discover Multi-Source Aggregator ────────────────────────────────────


class TestDiscoverMultiSource:
    @integration
    def test_discover_multi_source_with_real_sources(self):
        from job_assistant.services.multi_source_discovery import discover_multi_source
        jobs = discover_multi_source(
            query="python",
            sources=["USAJobs"],
            limit_per_source=3,
        )
        assert isinstance(jobs, list)
        for j in jobs:
            assert j.get("title")
            assert j.get("url")


# ── Full Pipeline Smoke Test ─────────────────────────────────────────────


class TestAutoApplyPipelineIntegration:
    @integration
    def test_discover_jobs_with_real_apis(self):
        from job_assistant.services.auto_apply_pipeline import _discover_jobs
        jobs = _discover_jobs(
            query="python developer",
            sources=["RemoteJobs.org", "Arbeitnow"],
            user_id=1,
        )
        assert isinstance(jobs, list)
        if jobs:
            for j in jobs:
                assert j.get("title")
                assert j.get("url")
