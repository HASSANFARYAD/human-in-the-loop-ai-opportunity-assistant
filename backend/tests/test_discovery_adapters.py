from __future__ import annotations

from job_assistant.services.job_source_scrapers import (
    IndeedScraper,
    SeekScraper,
    LinkedInScraper,
    UnsupportedSourceUrl,
    _dedupe_opportunities,
    get_scraper_for_url,
    is_job_listing_url,
)


# ── _dedupe() / _content_hash (public_discovery) ────────────────────────

class TestPublicDiscoveryDedup:
    def test_dedup_by_url_keeps_first(self):
        from job_assistant.services.public_discovery import _dedupe
        jobs = [
            {"title": "Eng A", "company": "Co", "url": "https://a.com/1", "description": "x"},
            {"title": "Eng A", "company": "Co", "url": "https://a.com/1", "description": "x"},
        ]
        result = _dedupe(jobs)
        assert len(result) == 1

    def test_dedup_by_content_hash_catches_same_content(self):
        from job_assistant.services.public_discovery import _dedupe
        jobs = [
            {"title": "SWE", "company": "Acme", "url": "https://a.com/1", "description": "Build stuff."},
            {"title": "SWE", "company": "Acme", "url": "https://b.com/2", "description": "Build stuff."},
        ]
        result = _dedupe(jobs)
        assert len(result) == 1

    def test_dedup_by_title_company_catches_repost(self):
        from job_assistant.services.public_discovery import _dedupe
        jobs = [
            {"title": "DevOps", "company": "CloudBase", "url": "https://a.com/1", "description": "Old desc."},
            {"title": "DevOps", "company": "CloudBase", "url": "https://a.com/2", "description": "New desc."},
        ]
        result = _dedupe(jobs)
        assert len(result) == 1

    def test_dedup_preserves_distinct_jobs(self):
        from job_assistant.services.public_discovery import _dedupe
        jobs = [
            {"title": "Role A", "company": "Co A", "url": "https://a.com/1", "description": "desc a"},
            {"title": "Role B", "company": "Co B", "url": "https://b.com/2", "description": "desc b"},
        ]
        result = _dedupe(jobs)
        assert len(result) == 2

    def test_dedup_catches_fuzzy_near_duplicate_title(self):
        from job_assistant.services.public_discovery import _dedupe
        jobs = [
            {"title": "Sr Frontend Engineer", "company": "Acme Corp", "url": "https://a.com/1", "description": "desc a"},
            {"title": "Senior Frontend Engineer", "company": "Acme Corp", "url": "https://a.com/2", "description": "desc b"},
        ]
        result = _dedupe(jobs)
        assert len(result) == 1

    def test_dedup_skips_empty_url(self):
        from job_assistant.services.public_discovery import _dedupe
        jobs = [
            {"title": "Role", "company": "Co", "url": "", "description": "desc"},
            {"title": "Role", "company": "Co", "url": "", "description": "desc"},
        ]
        result = _dedupe(jobs)
        assert len(result) == 1

    def test_content_hash_implementation(self):
        from job_assistant.services.public_discovery import _content_hash as pd_ch
        hashes = [pd_ch({"title": t, "company": c, "description": d}) for t, c, d in [
            ("SWE", "Acme", "desc"),
            ("swe", "acme", "DESC"),
        ]]
        assert hashes[0] == hashes[1]

    def test_content_hash_consistent_across_modules(self):
        from job_assistant.db import _content_hash as db_ch
        from job_assistant.services.public_discovery import _content_hash as pd_ch
        from job_assistant.services.job_source_scrapers import _content_hash as js_ch
        job = {"title": "Foo", "company": "Bar", "description": "Baz qux."}
        assert db_ch(job) == pd_ch(job) == js_ch(job)


# ── _matches_query() ────────────────────────────────────────────────────

class TestMatchesQuery:
    def test_match_on_title(self):
        from job_assistant.services.public_discovery import _matches_query
        assert _matches_query({"title": "Senior Engineer Python"}, "python") is True

    def test_match_on_company(self):
        from job_assistant.services.public_discovery import _matches_query
        assert _matches_query({"company": "Google"}, "google") is True

    def test_no_match(self):
        from job_assistant.services.public_discovery import _matches_query
        assert _matches_query({"title": "Engineer", "description": "Java"}, "python") is False

    def test_empty_query_matches_all(self):
        from job_assistant.services.public_discovery import _matches_query
        assert _matches_query({"title": "Anything"}, "") is True

    def test_match_multiple_terms(self):
        from job_assistant.services.public_discovery import _matches_query
        assert _matches_query({"title": "Senior Python Dev", "description": "Remote"}, "python remote") is True

    def test_match_partial_term(self):
        from job_assistant.services.public_discovery import _matches_query
        assert _matches_query({"title": "Senior Engineer"}, "senior") is True


# ── is_job_listing_url() ────────────────────────────────────────────────

class TestIsJobListingUrl:
    def test_valid_indeed_search(self):
        assert is_job_listing_url("https://www.indeed.com/jobs?q=python")

    def test_valid_indeed_q_path(self):
        assert is_job_listing_url("https://www.indeed.com/q-python-jobs.html")

    def test_valid_indeed_collections(self):
        assert is_job_listing_url("https://www.indeed.com/jobs/collections/remote")

    def test_valid_seek_url(self):
        assert is_job_listing_url("https://www.seek.com.au/jobs")

    def test_valid_seek_search(self):
        assert is_job_listing_url("https://www.seek.com.au/python-jobs")

    def test_valid_linkedin_url(self):
        assert is_job_listing_url("https://www.linkedin.com/jobs/search/?keywords=python")

    def test_invalid_empty(self):
        assert is_job_listing_url("") is False

    def test_invalid_non_url(self):
        assert is_job_listing_url("not a url") is False


# ── get_scraper_for_url() ───────────────────────────────────────────────

class TestGetScraperForUrl:
    def test_returns_indeed_scraper(self):
        scraper = get_scraper_for_url("https://www.indeed.com/jobs?q=python")
        assert isinstance(scraper, IndeedScraper)

    def test_returns_seek_scraper(self):
        scraper = get_scraper_for_url("https://www.seek.com.au/jobs")
        assert isinstance(scraper, SeekScraper)

    def test_returns_linkedin_scraper(self):
        scraper = get_scraper_for_url("https://www.linkedin.com/jobs/search/?keywords=python")
        assert isinstance(scraper, LinkedInScraper)

    def test_unsupported_url_raises(self):
        import pytest
        with pytest.raises(UnsupportedSourceUrl):
            get_scraper_for_url("https://example.com/jobs")


# ── IndeedScraper.supports() ────────────────────────────────────────────

class TestIndeedScraperSupports:
    def setup_method(self):
        self.scraper = IndeedScraper()

    def test_supports_indeed_url(self):
        assert self.scraper.supports("https://www.indeed.com/jobs?q=python")
        assert self.scraper.supports("https://de.indeed.com/Jobs")

    def test_supports_manual_source(self):
        assert self.scraper.supports("https://www.indeed.com/jobs", source="manual")

    def test_does_not_support_linkedin(self):
        assert self.scraper.supports("https://linkedin.com/jobs") is False

    def test_does_not_support_linkedin_source(self):
        assert self.scraper.supports("https://www.indeed.com/jobs", source="linkedin") is False


# ── SeekScraper.supports() ──────────────────────────────────────────────

class TestSeekScraperSupports:
    def setup_method(self):
        self.scraper = SeekScraper()

    def test_supports_seek_url(self):
        assert self.scraper.supports("https://www.seek.com.au/jobs")
        assert self.scraper.supports("https://www.seek.com.au/python-jobs")

    def test_supports_manual_source(self):
        assert self.scraper.supports("https://www.seek.com.au/jobs", source="manual")

    def test_does_not_support_indeed(self):
        assert self.scraper.supports("https://www.indeed.com/jobs") is False


# ── LinkedInScraper.supports() ──────────────────────────────────────────

class TestLinkedInScraperSupports:
    def setup_method(self):
        self.scraper = LinkedInScraper()

    def test_supports_linkedin_url(self):
        assert self.scraper.supports("https://www.linkedin.com/jobs/search/?keywords=python")
        assert self.scraper.supports("https://www.linkedin.com/jobs/")

    def test_supports_manual_source(self):
        assert self.scraper.supports("https://www.linkedin.com/jobs/", source="manual")

    def test_does_not_support_indeed(self):
        assert self.scraper.supports("https://www.indeed.com/jobs") is False


# ── seek_page_urls() ────────────────────────────────────────────────────

class TestSeekPageUrls:
    def test_generates_single_page(self):
        from job_assistant.services.job_source_scrapers import seek_page_urls
        urls = seek_page_urls("https://www.seek.com.au/jobs", page_limit=1)
        assert len(urls) == 1
        assert "page" not in urls[0]

    def test_generates_multi_page(self):
        from job_assistant.services.job_source_scrapers import seek_page_urls
        urls = seek_page_urls("https://www.seek.com.au/python-jobs", page_limit=2)
        assert len(urls) == 2
        assert "page=2" in urls[1]


# ── _dedupe_opportunities() (job_source_scrapers) ───────────────────────

class TestScrapersDedup:
    def test_dedup_url(self):
        jobs = [
            {"title": "A", "company": "Co", "url": "https://x.com/1", "description": "d1"},
            {"title": "A", "company": "Co", "url": "https://x.com/1", "description": "d1"},
        ]
        assert len(_dedupe_opportunities(jobs)) == 1

    def test_dedup_content_hash(self):
        jobs = [
            {"title": "SWE", "company": "Acme", "url": "https://a.com/1", "description": "Same desc"},
            {"title": "SWE", "company": "Acme", "url": "https://b.com/2", "description": "Same desc"},
        ]
        assert len(_dedupe_opportunities(jobs)) == 1

    def test_dedup_title_company(self):
        jobs = [
            {"title": "DevOps", "company": "CloudBase", "url": "https://a.com/1", "description": "Desc 1"},
            {"title": "DevOps", "company": "CloudBase", "url": "https://a.com/2", "description": "Desc 2"},
        ]
        assert len(_dedupe_opportunities(jobs)) == 1

    def test_dedup_preserves_distinct(self):
        jobs = [
            {"title": "A", "company": "Co A", "url": "https://a.com/1", "description": "desc a"},
            {"title": "B", "company": "Co B", "url": "https://b.com/2", "description": "desc b"},
        ]
        assert len(_dedupe_opportunities(jobs)) == 2

    def test_dedup_catches_fuzzy_near_duplicate(self):
        jobs = [
            {"title": "Sr DevOps", "company": "CloudBase", "url": "https://x.com/1", "description": "d1"},
            {"title": "Senior DevOps", "company": "CloudBase", "url": "https://x.com/2", "description": "d2"},
        ]
        assert len(_dedupe_opportunities(jobs)) == 1


# ── fetch_remoteok() ─────────────────────────────────────────────────────

class TestFetchRemoteOk:
    def test_parses_response(self, monkeypatch):
        from job_assistant.services import public_discovery
        fake_json = [
            {"last_updated": 123, "legal": "terms"},
            {
                "slug": "senior-python-dev-acme-123",
                "id": "123",
                "epoch": 1782316803,
                "date": "2026-06-24T16:00:03+00:00",
                "company": "Acme Corp",
                "company_logo": "",
                "position": "Senior Python Developer",
                "tags": ["python", "django", "remote"],
                "description": "<p>Build APIs with Python and Django.</p>",
                "location": "Remote",
            },
        ]

        def fake_get(url, timeout):
            class FakeResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return fake_json
            return FakeResponse()

        monkeypatch.setattr(public_discovery.requests, "get", fake_get)
        result = public_discovery.fetch_remoteok(limit=20)
        assert len(result) == 1
        assert result[0]["title"] == "Senior Python Developer"
        assert result[0]["company"] == "Acme Corp"
        assert result[0]["location"] == "Remote"
        assert result[0]["url"] == "https://remoteok.com/remote-jobs/senior-python-dev-acme-123"
        assert result[0]["source"] == "RemoteOK"
        assert result[0]["date_received"] == "2026-06-24"
        assert "python" in result[0]["raw_text"]

    def test_respects_limit(self, monkeypatch):
        from job_assistant.services import public_discovery
        fake_json = [{"last_updated": 0, "legal": "t"}]
        for i in range(10):
            fake_json.append({
                "slug": f"job-{i}",
                "id": str(i),
                "epoch": 1782316800,
                "date": "2026-06-24T00:00:00Z",
                "company": "Co",
                "position": f"Job {i}",
                "tags": [],
                "description": f"desc {i}",
                "location": "",
            })

        def fake_get(url, timeout):
            class FakeResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return fake_json
            return FakeResponse()

        monkeypatch.setattr(public_discovery.requests, "get", fake_get)
        result = public_discovery.fetch_remoteok(limit=5)
        assert len(result) == 5

    def test_skips_meta_item(self, monkeypatch):
        from job_assistant.services import public_discovery
        fake_json = [
            {"last_updated": 123, "legal": "terms"},
        ]

        def fake_get(url, timeout):
            class FakeResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return fake_json
            return FakeResponse()

        monkeypatch.setattr(public_discovery.requests, "get", fake_get)
        result = public_discovery.fetch_remoteok(limit=20)
        assert len(result) == 0


# ── fetch_muse() ─────────────────────────────────────────────────────────

class TestFetchMuse:
    def test_parses_response(self, monkeypatch):
        from job_assistant.services import public_discovery
        fake_json = {
            "results": [
                {
                    "name": "Software Engineer",
                    "id": 123,
                    "publication_date": "2026-06-20T10:00:00Z",
                    "contents": "<p>Join our team building cool stuff.</p>",
                    "type": "external",
                    "locations": [{"name": "San Francisco, CA"}],
                    "categories": [{"name": "Engineering"}],
                    "levels": [{"name": "Mid Level", "short_name": "mid"}],
                    "company": {"id": 456, "short_name": "techco", "name": "TechCo"},
                    "refs": {"landing_page": "https://themuse.com/jobs/techco/software-engineer"},
                }
            ]
        }

        def fake_get(url, timeout, **kwargs):
            class FakeResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return fake_json
            return FakeResponse()

        monkeypatch.setattr(public_discovery.requests, "get", fake_get)
        result = public_discovery.fetch_muse(limit=20)
        assert len(result) == 1
        assert result[0]["title"] == "Software Engineer"
        assert result[0]["company"] == "TechCo"
        assert result[0]["location"] == "San Francisco, CA"
        assert result[0]["url"] == "https://themuse.com/jobs/techco/software-engineer"
        assert result[0]["source"] == "The Muse"
        assert result[0]["date_received"] == "2026-06-20"

    def test_handles_missing_company(self, monkeypatch):
        from job_assistant.services import public_discovery
        fake_json = {
            "results": [
                {
                    "name": "Mystery Job",
                    "id": 789,
                    "publication_date": "2026-06-01T00:00:00Z",
                    "contents": "No company listed.",
                    "type": "external",
                    "locations": [],
                    "categories": [],
                    "levels": [],
                    "company": {},
                    "refs": {"landing_page": ""},
                }
            ]
        }

        def fake_get(url, timeout, **kwargs):
            class FakeResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return fake_json
            return FakeResponse()

        monkeypatch.setattr(public_discovery.requests, "get", fake_get)
        result = public_discovery.fetch_muse(limit=20)
        assert len(result) == 1
        assert result[0]["company"] == ""
        assert result[0]["location"] == ""
        assert result[0]["url"] == ""

    def test_returns_empty_on_no_results(self, monkeypatch):
        from job_assistant.services import public_discovery
        fake_json = {"results": []}

        def fake_get(url, timeout, **kwargs):
            class FakeResponse:
                def raise_for_status(self):
                    pass
                def json(self):
                    return fake_json
            return FakeResponse()

        monkeypatch.setattr(public_discovery.requests, "get", fake_get)
        result = public_discovery.fetch_muse(limit=20)
        assert len(result) == 0
