from __future__ import annotations

from job_assistant.db import _fuzzy_match_title_company, _normalize_for_fuzzy, FUZZY_DUP_THRESHOLD


class TestFuzzyMatching:
    def test_normalize_strips_punctuation_and_case(self):
        assert _normalize_for_fuzzy("Senior Frontend Engineer!") == "senior frontend engineer"
        assert _normalize_for_fuzzy("  Sr. DevOps  ") == "senior devops"

    def test_fuzzy_match_catches_sr_vs_senior(self):
        assert _fuzzy_match_title_company("Sr Frontend Engineer", "Acme Corp", [("Senior Frontend Engineer", "Acme Corp")])
        assert _fuzzy_match_title_company("Sr Frontend Engineer", "Acme Corp", [("senior frontend engineer", "acme corp")])

    def test_fuzzy_match_rejects_different_roles(self):
        assert not _fuzzy_match_title_company("Frontend Engineer", "Acme Corp", [("Backend Engineer", "Acme Corp")])

    def test_fuzzy_match_rejects_different_companies(self):
        assert not _fuzzy_match_title_company("Software Engineer", "Google", [("Software Engineer", "Facebook")])

    def test_fuzzy_match_empty_title_or_company(self):
        assert not _fuzzy_match_title_company("", "Acme", [("Engineer", "Acme")])
        assert not _fuzzy_match_title_company("Engineer", "", [("Engineer", "Acme")])
        assert not _fuzzy_match_title_company("Engineer", "Acme", [("", "Acme")])

    def test_fuzzy_match_empty_existing_list(self):
        assert not _fuzzy_match_title_company("Engineer", "Acme", [])

    def test_fuzzy_match_catches_abbreviation_vs_full(self):
        assert _fuzzy_match_title_company("Sr. Software Eng", "IBM", [("Senior Software Engineer", "IBM")])

    def test_fuzzy_match_preserves_distinct(self):
        assert not _fuzzy_match_title_company("DevOps Engineer", "Co A", [("Data Scientist", "Co B")])

    def test_normalize_removes_extra_whitespace(self):
        assert _normalize_for_fuzzy("  Senior   Engineer  ") == "senior engineer"


def _sample_entry() -> dict:
    return {
        "title": "Senior Frontend Engineer",
        "company": "Acme Corp",
        "description": (
            "We are hiring a Senior Frontend Engineer. "
            "Responsibilities: build React components, optimize performance. "
            "Requirements: 5+ years React, TypeScript, CSS. "
            "Full-time, remote. Apply now."
        ),
        "raw_text": (
            "We are hiring a Senior Frontend Engineer. "
            "Responsibilities: build React components, optimize performance. "
            "Requirements: 5+ years React, TypeScript, CSS. "
            "Full-time, remote. Apply now."
        ),
        "source": "Manual",
        "opportunity_type": "job",
        "url": "",
        "location": "",
        "remote_type": "",
    }


def _sample_discovered_entry() -> dict:
    return {
        "title": "Senior Frontend Engineer",
        "company": "Acme Corp",
        "description": (
            "We are hiring a Senior Frontend Engineer. "
            "Responsibilities: build React components, optimize performance. "
            "Requirements: 5+ years React, TypeScript, CSS. "
            "Full-time, remote. Apply now."
        ),
        "raw_text": (
            "We are hiring a Senior Frontend Engineer. "
            "Responsibilities: build React components, optimize performance. "
            "Requirements: 5+ years React, TypeScript, CSS. "
            "Full-time, remote. Apply now."
        ),
        "source": "RemoteJobs.org",
        "date_received": "2026-06-22",
        "opportunity_type": "job",
        "url": "https://remotejobs.org/jobs/123",
        "location": "Remote",
        "remote_type": "Remote",
        "salary_min": 120000,
        "salary_max": 160000,
    }


def test_manual_entry_runs_same_pipeline_as_discovered(monkeypatch):
    from job_assistant.services import job_import

    inserted: list[dict] = []

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    def fake_job_exists(job, user_id=1, workspace_id=None):
        return False

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_exists", fake_job_exists)

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    manual = _sample_entry()
    discovered = _sample_discovered_entry()

    manual_annotated = annotate_opportunity(manual)
    discovered_annotated = annotate_opportunity(discovered)

    result_manual = job_import.import_opportunities([manual_annotated], user_id=1)
    result_discovered = job_import.import_opportunities([discovered_annotated], user_id=1)

    assert result_manual.imported == 1
    assert result_discovered.imported == 1
    assert len(inserted) == 2

    stored_manual = inserted[0]
    stored_discovered = inserted[1]

    assert stored_manual["title"] == stored_discovered["title"] == "Senior Frontend Engineer"
    assert stored_manual["company"] == stored_discovered["company"] == "Acme Corp"
    assert stored_manual["classification"] == stored_discovered["classification"] == "job"
    assert stored_manual["importable"] == stored_discovered["importable"]
    assert stored_manual["opportunity_type"] == stored_discovered["opportunity_type"]
    assert stored_manual["source"] == "Manual"
    assert stored_discovered["source"] == "RemoteJobs.org"


def test_manual_entry_with_url_detects_duplicate(monkeypatch):
    from job_assistant.services import job_import

    inserted: list[dict] = []
    existing_jobs: list[dict] = []

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        existing_jobs.append(dict(job))
        return len(inserted)

    def fake_job_exists(job, user_id=1, workspace_id=None):
        url = (job.get("url") or "").strip()
        if url:
            for existing in existing_jobs:
                if existing.get("url") == url:
                    return True
        return False

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_exists", fake_job_exists)

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    entry = _sample_entry()
    entry["url"] = "https://example.com/jobs/456"

    annotated = annotate_opportunity(entry)
    result1 = job_import.import_opportunities([annotated], user_id=1)
    assert result1.imported == 1
    assert result1.skipped_duplicates == 0

    annotated2 = annotate_opportunity(entry)
    result2 = job_import.import_opportunities([annotated2], user_id=1)
    assert result2.imported == 0
    assert result2.skipped_duplicates == 1


def _make_tracking_fake_job_exists() -> tuple[list[dict], callable]:
    """Build a fake_job_exists that tracks inserted jobs and checks
    URL, content_hash, and title+company."""
    from job_assistant.db import _content_hash

    existing: list[dict] = []

    def _exists(job, user_id=1, workspace_id=None):
        url = (job.get("url") or "").strip()
        title = (job.get("title") or "").strip()
        company = (job.get("company") or "").strip()
        ch = _content_hash(job)
        for stored in existing:
            if url and stored.get("url") == url:
                return True
            if ch == stored.get("content_hash"):
                return True
            if title and company and stored.get("title") == title and stored.get("company") == company:
                return True
        return False

    return existing, _exists


def test_same_job_different_sources_caught_by_hash(monkeypatch):
    """Same job on two sources with different URLs caught by content_hash."""
    from job_assistant.services import job_import

    inserted, fake_exists = _make_tracking_fake_job_exists()

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_exists", fake_exists)

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    source_a = annotate_opportunity({
        "title": "Python Developer",
        "company": "DataFlow Inc",
        "description": "We are hiring a Python Developer. Requirements: 3+ years Python, SQL, FastAPI. Apply now.",
        "raw_text": "We are hiring a Python Developer. Requirements: 3+ years Python, SQL, FastAPI. Apply now.",
        "url": "https://remotejobs.org/jobs/aaa",
        "source": "RemoteJobs.org",
        "opportunity_type": "job",
    })
    source_b = annotate_opportunity({
        "title": "Python Developer",
        "company": "DataFlow Inc",
        "description": "We are hiring a Python Developer. Requirements: 3+ years Python, SQL, FastAPI. Apply now.",
        "raw_text": "We are hiring a Python Developer. Requirements: 3+ years Python, SQL, FastAPI. Apply now.",
        "url": "https://arbeitnow.com/jobs/bbb",
        "source": "Arbeitnow",
        "opportunity_type": "job",
    })

    result1 = job_import.import_opportunities([source_a], user_id=1)
    assert result1.imported == 1

    result2 = job_import.import_opportunities([source_b], user_id=1)
    assert result2.imported == 0
    assert result2.skipped_duplicates == 1


def test_same_job_reposted_with_new_id_date_caught_by_tc(monkeypatch):
    """Same job re-posted with new URL/date but same title+company caught by title+company."""
    from job_assistant.services import job_import

    inserted, fake_exists = _make_tracking_fake_job_exists()

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_exists", fake_exists)

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    original = annotate_opportunity({
        "title": "DevOps Engineer",
        "company": "CloudBase",
        "description": "We are hiring a DevOps Engineer. Requirements: AWS, Docker, Kubernetes.",
        "raw_text": "We are hiring a DevOps Engineer. Requirements: AWS, Docker, Kubernetes.",
        "url": "https://example.com/old-post",
        "date_received": "2026-06-01",
        "source": "RemoteJobs.org",
        "opportunity_type": "job",
    })
    repost = annotate_opportunity({
        "title": "DevOps Engineer",
        "company": "CloudBase",
        "description": "We are hiring a DevOps Engineer. Requirements: AWS, Docker, Kubernetes, CI/CD.",
        "raw_text": "We are hiring a DevOps Engineer. Requirements: AWS, Docker, Kubernetes, CI/CD.",
        "url": "https://example.com/new-post",
        "date_received": "2026-06-22",
        "source": "RemoteJobs.org",
        "opportunity_type": "job",
    })

    result1 = job_import.import_opportunities([original], user_id=1)
    assert result1.imported == 1

    result2 = job_import.import_opportunities([repost], user_id=1)
    assert result2.imported == 0
    assert result2.skipped_duplicates == 1


def test_near_duplicate_title_not_caught(monkeypatch):
    """Near-duplicate with different descriptions across separate batches
    is only caught if job_exists returns True. This test uses fake_job_exists=False
    to document that cross-batch dedup depends on DB-level fuzzy checking."""
    from job_assistant.services import job_import

    inserted: list[dict] = []

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    def fake_job_exists(job, user_id=1, workspace_id=None):
        return False

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_exists", fake_job_exists)

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    job_a = annotate_opportunity({
        "title": "Sr Frontend Engineer",
        "company": "Acme Corp",
        "description": "We are hiring a Senior Frontend Engineer with React experience. Apply now.",
        "raw_text": "We are hiring a Senior Frontend Engineer with React experience. Apply now.",
        "url": "https://example.com/job-a",
        "opportunity_type": "job",
    })
    job_b = annotate_opportunity({
        "title": "Senior Frontend Engineer",
        "company": "Acme Corp",
        "description": "Acme Corp is looking for a Senior Frontend Engineer with strong React and TypeScript skills. Full-time remote. Apply today.",
        "raw_text": "Acme Corp is looking for a Senior Frontend Engineer with strong React and TypeScript skills. Full-time remote. Apply today.",
        "url": "https://example.com/job-b",
        "opportunity_type": "job",
    })

    result1 = job_import.import_opportunities([job_a], user_id=1)
    assert result1.imported == 1

    result2 = job_import.import_opportunities([job_b], user_id=1)
    assert result2.imported == 1
    assert result2.skipped_duplicates == 0


def test_fuzzy_dedup_catches_near_duplicate_in_same_batch(monkeypatch):
    """Near-duplicate titles in the same import batch are caught by fuzzy matching."""
    from job_assistant.services import job_import

    inserted: list[dict] = []

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    def fake_job_exists(job, user_id=1, workspace_id=None):
        return False

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_exists", fake_job_exists)

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    job_a = annotate_opportunity({
        "title": "Sr Frontend Engineer",
        "company": "Acme Corp",
        "description": "We are hiring a Senior Frontend Engineer with React experience. Requirements: 3+ years React. Apply now.",
        "raw_text": "We are hiring a Senior Frontend Engineer with React experience. Requirements: 3+ years React. Apply now.",
        "url": "https://example.com/job-a",
        "opportunity_type": "job",
    })
    job_b = annotate_opportunity({
        "title": "Senior Frontend Engineer",
        "company": "Acme Corp",
        "description": "Senior Frontend role with strong React and TypeScript skills. Requirements: 5+ years React. Apply now.",
        "raw_text": "Senior Frontend role with strong React and TypeScript skills. Requirements: 5+ years React. Apply now.",
        "url": "https://example.com/job-b",
        "opportunity_type": "job",
    })

    result = job_import.import_opportunities([job_a, job_b], user_id=1)
    assert result.imported == 1
    assert result.skipped_duplicates == 1


def test_fuzzy_dedup_preserves_distinct_in_same_batch(monkeypatch):
    """Distinct titles in the same batch are not caught by fuzzy matching."""
    from job_assistant.services import job_import

    inserted: list[dict] = []

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    def fake_job_exists(job, user_id=1, workspace_id=None):
        return False

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_exists", fake_job_exists)

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    job_a = annotate_opportunity({
        "title": "Frontend Engineer",
        "company": "Acme Corp",
        "description": "We are hiring a Frontend Engineer. Requirements: React, TypeScript. Apply now.",
        "raw_text": "We are hiring a Frontend Engineer. Requirements: React, TypeScript. Apply now.",
        "url": "https://example.com/job-a",
        "opportunity_type": "job",
    })
    job_b = annotate_opportunity({
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "description": "We are hiring a Backend Engineer. Requirements: Python, SQL. Apply now.",
        "raw_text": "We are hiring a Backend Engineer. Requirements: Python, SQL. Apply now.",
        "url": "https://example.com/job-b",
        "opportunity_type": "job",
    })

    result = job_import.import_opportunities([job_a, job_b], user_id=1)
    assert result.imported == 2
    assert result.skipped_duplicates == 0


def test_content_hash_differs_for_distinct_jobs():
    from job_assistant.db import _content_hash
    from job_assistant.services.public_discovery import _content_hash as pd_ch

    job1 = {"title": "Backend Engineer", "company": "Co A", "description": "Python, SQL"}
    job2 = {"title": "Frontend Engineer", "company": "Co B", "description": "React, CSS"}

    h1 = _content_hash(job1)
    h2 = _content_hash(job2)

    assert h1 != h2
    assert len(h1) == 64
    assert len(h2) == 64

    assert pd_ch(job1) == h1


def test_content_hash_is_case_and_whitespace_normalized():
    from job_assistant.services.public_discovery import _content_hash

    job_a = {"title": "  Senior Engineer  ", "company": "Acme", "description": "  Some Description  "}
    job_b = {"title": "senior engineer", "company": "acme", "description": "some description"}

    assert _content_hash(job_a) == _content_hash(job_b)


def test_manual_entry_classified_as_job(monkeypatch):
    from job_assistant.services.opportunity_classifier import annotate_opportunity

    entry = _sample_entry()
    annotated = annotate_opportunity(entry)

    assert annotated.get("classification") == "job"
    assert annotated.get("importable") is True
    assert annotated.get("opportunity_confidence", 0) >= 0.3
