from __future__ import annotations

from job_assistant.services.job_source_scrapers import (
    IndeedScraper,
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

    def test_invalid_non_indeed(self):
        assert is_job_listing_url("https://linkedin.com/jobs") is False

    def test_invalid_empty(self):
        assert is_job_listing_url("") is False

    def test_invalid_non_url(self):
        assert is_job_listing_url("not a url") is False


# ── get_scraper_for_url() ───────────────────────────────────────────────

class TestGetScraperForUrl:
    def test_returns_indeed_scraper(self):
        scraper = get_scraper_for_url("https://www.indeed.com/jobs?q=python")
        assert isinstance(scraper, IndeedScraper)

    def test_unsupported_url_raises(self):
        import pytest
        with pytest.raises(UnsupportedSourceUrl):
            get_scraper_for_url("https://linkedin.com/jobs")


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
