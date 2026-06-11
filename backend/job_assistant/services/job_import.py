from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from job_assistant.db import insert_job, job_url_exists
from job_assistant.services.opportunity_classifier import (
    VALID_OPPORTUNITY_CATEGORIES,
    annotate_opportunity,
    extract_opportunities_from_container,
)


@dataclass
class ImportResult:
    found: int = 0
    imported: int = 0
    skipped_duplicates: int = 0
    ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped_non_opportunities: int = 0
    extracted: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "imported": self.imported,
            "skipped_duplicates": self.skipped_duplicates,
            "ids": self.ids,
            "errors": self.errors,
            "warnings": self.warnings,
            "skipped_non_opportunities": self.skipped_non_opportunities,
            "extracted": self.extracted,
        }


def import_opportunities(
    opportunities: list[dict[str, Any]],
    user_id: int,
    workspace_id: int | None = None,
) -> ImportResult:
    result = ImportResult(found=len(opportunities))
    seen_urls: set[str] = set()
    expanded: list[dict[str, Any]] = []
    for item in opportunities:
        annotated = annotate_opportunity(item)
        if annotated.get("classification") not in VALID_OPPORTUNITY_CATEGORIES and not annotated.get("importable"):
            extracted = extract_opportunities_from_container(annotated)
            if extracted:
                result.extracted += len(extracted)
                expanded.extend(extracted)
            else:
                result.skipped_non_opportunities += 1
                result.warnings.append(
                    f"{item.get('title') or item.get('subject') or 'Source item'} skipped: {annotated.get('blocked_reason') or annotated.get('classification_reason')}"
                )
            continue
        expanded.append(annotated)

    result.found = len(expanded)
    for item in expanded:
        if not item.get("importable"):
            result.skipped_non_opportunities += 1
            result.warnings.append(
                f"{item.get('title') or item.get('url') or 'Opportunity'} skipped: {item.get('blocked_reason') or 'low confidence'}"
            )
            continue
        url = str(item.get("url") or "").strip()
        if url:
            if url in seen_urls or job_url_exists(url, user_id=user_id, workspace_id=workspace_id):
                result.skipped_duplicates += 1
                continue
            seen_urls.add(url)
        try:
            result.ids.append(insert_job(item, user_id, workspace_id=workspace_id))
            result.imported += 1
        except Exception as exc:
            result.errors.append(f"{item.get('title') or url or 'Untitled opportunity'}: {exc}")
    return result
