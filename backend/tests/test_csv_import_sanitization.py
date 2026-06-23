from __future__ import annotations

import importlib.util
import io

import pytest

from job_assistant.services.parsing import (
    jobs_from_csv,
    neutralize_csv_formula,
    sanitize_imported_text,
)

_HAS_PANDAS = importlib.util.find_spec("pandas") is not None
requires_pandas = pytest.mark.skipif(not _HAS_PANDAS, reason="pandas required for CSV parsing")


def test_neutralize_csv_formula_prefixes_risky_cells():
    assert neutralize_csv_formula("=SUM(A1:A2)") == "'=SUM(A1:A2)"
    assert neutralize_csv_formula("+1234") == "'+1234"
    assert neutralize_csv_formula("-1+1") == "'-1+1"
    assert neutralize_csv_formula("@cmd") == "'@cmd"
    assert neutralize_csv_formula("\t=evil") == "'\t=evil"


def test_neutralize_csv_formula_leaves_safe_text():
    assert neutralize_csv_formula("Senior Engineer") == "Senior Engineer"
    assert neutralize_csv_formula("https://example.com/job") == "https://example.com/job"


def test_sanitize_imported_text_strips_html_and_controls():
    assert sanitize_imported_text("<b>Hi</b>") == "Hi"
    assert sanitize_imported_text("clean\x00text") == "cleantext"


def test_sanitize_imported_text_truncates():
    assert sanitize_imported_text("x" * 100, max_length=10) == "x" * 10


def test_sanitize_imported_text_passes_through_non_strings():
    assert sanitize_imported_text(None) is None
    assert sanitize_imported_text(42) == 42


@requires_pandas
def test_jobs_from_csv_neutralizes_formula_injection():
    csv_content = (
        "title,company,description\n"
        '=cmd|calc,@evil,"=HYPERLINK(""http://x"")"\n'
    )
    jobs = jobs_from_csv(io.StringIO(csv_content))
    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"].startswith("'=cmd")
    assert job["company"].startswith("'@evil")
    assert job["description"].startswith("'=HYPERLINK")


@requires_pandas
def test_jobs_from_csv_strips_html_in_description():
    csv_content = (
        "title,description\n"
        'Engineer,"<p>Build <b>APIs</b></p>"\n'
    )
    jobs = jobs_from_csv(io.StringIO(csv_content))
    assert "<p>" not in jobs[0]["description"]
    assert "APIs" in jobs[0]["description"]
