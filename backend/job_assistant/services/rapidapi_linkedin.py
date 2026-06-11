from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

import requests


DEFAULT_HOST = "linkedin-job-search-api.p.rapidapi.com"
DEFAULT_ENDPOINT = "https://linkedin-job-search-api.p.rapidapi.com/active-jb-1h"


def search_linkedin_jobs(
    api_key: str,
    title_filter: str,
    location_filter: str,
    offset: int = 0,
    host: str = DEFAULT_HOST,
    endpoint: str = DEFAULT_ENDPOINT,
) -> List[Dict[str, Any]]:
    if not api_key.strip():
        raise ValueError("Missing RapidAPI key.")
    if not title_filter.strip():
        raise ValueError("Title/search filter is required.")

    response = requests.get(
        endpoint.strip() or DEFAULT_ENDPOINT,
        headers={
            "x-rapidapi-key": api_key.strip(),
            "x-rapidapi-host": host.strip() or DEFAULT_HOST,
            "Content-Type": "application/json",
        },
        params={
            "offset": str(max(0, offset)),
            "title_filter": title_filter.strip(),
            "location_filter": location_filter.strip(),
            "description_type": "text",
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    return _extract_items(payload)


def rapidapi_items_to_opportunities(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    for item in items:
        title = _first(item, ["title", "job_title", "jobTitle", "position", "name"])
        url = _first(item, ["url", "job_url", "jobUrl", "apply_url", "applyUrl", "link"])
        description = _first(item, ["description", "job_description", "jobDescription", "text"])
        if not title and not url and not description:
            continue
        opportunities.append(
            {
                "title": title or url or "Untitled LinkedIn job",
                "company": _first(item, ["company", "company_name", "companyName", "organization"]),
                "location": _first(item, ["location", "job_location", "jobLocation"]),
                "remote_type": _infer_remote_type(item),
                "url": url,
                "source": "RapidAPI LinkedIn Jobs",
                "date_received": _first(item, ["date", "posted_at", "postedAt", "created_at", "createdAt"])[:10],
                "description": description,
                "recruiter_email": _first(item, ["recruiter_email", "recruiterEmail", "email"]),
                "salary_min": item.get("salary_min") or item.get("salaryMin"),
                "salary_max": item.get("salary_max") or item.get("salaryMax"),
                "deadline": _first(item, ["deadline", "validThrough"]),
                "opportunity_type": "job",
                "raw_text": json.dumps(item, ensure_ascii=False),
            }
        )
    return opportunities


def _extract_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["data", "jobs", "results", "items"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def _first(item: Dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        text = str(value).strip()
        if text:
            return text
    return ""


def _infer_remote_type(item: Dict[str, Any]) -> str:
    text = json.dumps(item, ensure_ascii=False).lower()
    return "Remote" if "remote" in text else ""
