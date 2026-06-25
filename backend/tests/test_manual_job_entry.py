from __future__ import annotations

from unittest.mock import ANY


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
    from job_assistant.services.opportunity_classifier import annotate_opportunity

    inserted: list[dict] = []

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    def fake_job_url_exists(url, user_id=1, workspace_id=None):
        return False

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_url_exists", fake_job_url_exists)

    manual = _sample_entry()
    discovered = _sample_discovered_entry()

    # Both go through annotate_opportunity first (as done in import_opportunities)
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
    existing_urls: set[str] = set()

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    def fake_job_url_exists(url, user_id=1, workspace_id=None):
        return url in existing_urls

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_url_exists", fake_job_url_exists)

    entry = _sample_entry()
    entry["url"] = "https://example.com/jobs/456"

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    annotated = annotate_opportunity(entry)
    result1 = job_import.import_opportunities([annotated], user_id=1)
    assert result1.imported == 1
    assert result1.skipped_duplicates == 0

    existing_urls.add("https://example.com/jobs/456")

    annotated2 = annotate_opportunity(entry)
    result2 = job_import.import_opportunities([annotated2], user_id=1)
    assert result2.imported == 0
    assert result2.skipped_duplicates == 1


def test_manual_entry_without_url_not_caught_as_duplicate_by_url_check(monkeypatch):
    """Documents a known gap: manual entries without a URL are not caught
    as duplicates since the current DB-level dedup keys on URL only."""
    from job_assistant.services import job_import

    inserted: list[dict] = []

    def fake_insert_job(job, user_id, workspace_id=None):
        inserted.append(dict(job))
        return len(inserted)

    def fake_job_url_exists(url, user_id=1, workspace_id=None):
        return False

    monkeypatch.setattr(job_import, "insert_job", fake_insert_job)
    monkeypatch.setattr(job_import, "job_url_exists", fake_job_url_exists)

    entry = _sample_entry()
    entry["url"] = ""

    from job_assistant.services.opportunity_classifier import annotate_opportunity

    annotated = annotate_opportunity(entry)
    result1 = job_import.import_opportunities([annotated], user_id=1)
    assert result1.imported == 1

    annotated2 = annotate_opportunity(entry)
    result2 = job_import.import_opportunities([annotated2], user_id=1)
    assert result2.imported == 1
    assert result2.skipped_duplicates == 0
    assert len(inserted) == 2


def test_manual_entry_classified_as_job(monkeypatch):
    from job_assistant.services.opportunity_classifier import annotate_opportunity

    entry = _sample_entry()
    annotated = annotate_opportunity(entry)

    assert annotated.get("classification") == "job"
    assert annotated.get("importable") is True
    assert annotated.get("opportunity_confidence", 0) >= 0.3
