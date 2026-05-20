from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List
from urllib.parse import quote

import requests


APIFY_SYNC_TIMEOUT_SECONDS = 300


def run_actor_for_items(api_token: str, actor_id: str, run_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not api_token.strip():
        raise ValueError("Missing Apify API token.")
    if not actor_id.strip():
        raise ValueError("Missing Apify actor id.")

    encoded_actor = quote(actor_id.strip(), safe="")
    url = f"https://api.apify.com/v2/acts/{encoded_actor}/run-sync-get-dataset-items"
    response = requests.post(
        url,
        params={"token": api_token.strip(), "clean": "true", "format": "json"},
        json=run_input,
        timeout=APIFY_SYNC_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def build_run_input(url: str, input_template: str = "") -> Dict[str, Any]:
    if input_template.strip():
        payload = json.loads(input_template)
    else:
        payload = {"startUrls": [{"url": url}]}
    return _replace_url_placeholders(payload, url)


def _replace_url_placeholders(value: Any, url: str) -> Any:
    if isinstance(value, str):
        return value.replace("{{url}}", url)
    if isinstance(value, list):
        return [_replace_url_placeholders(item, url) for item in value]
    if isinstance(value, dict):
        return {key: _replace_url_placeholders(item, url) for key, item in value.items()}
    return value


def apify_items_to_opportunities(items: Iterable[Dict[str, Any]], source: str = "Apify") -> List[Dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    for item in items:
        title = _first(item, ["title", "jobTitle", "position", "name", "job_title"])
        url = _first(item, ["url", "jobUrl", "job_url", "applyUrl", "apply_url", "link"])
        description = _first(item, ["description", "jobDescription", "job_description", "text", "snippet"])
        if not title and not description and not url:
            continue
        opportunities.append(
            {
                "title": title or url or "Untitled scraped job",
                "company": _first(item, ["company", "companyName", "company_name", "organization", "employer"]),
                "location": _first(item, ["location", "jobLocation", "job_location", "city", "country"]),
                "remote_type": _infer_remote_type(item),
                "url": url,
                "source": source,
                "date_received": _first(item, ["date", "postedAt", "posted_at", "publishedAt", "createdAt"])[:10],
                "description": description,
                "recruiter_email": _first(item, ["recruiterEmail", "email"]),
                "salary_min": item.get("salary_min") or item.get("salaryMin"),
                "salary_max": item.get("salary_max") or item.get("salaryMax"),
                "deadline": _first(item, ["deadline", "validThrough"]),
                "opportunity_type": "job",
                "raw_text": json.dumps(item, ensure_ascii=False),
            }
        )
    return opportunities


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
    remote_value = item.get("remote") or item.get("isRemote") or item.get("remote_type") or item.get("workplaceType")
    if isinstance(remote_value, bool):
        return "Remote" if remote_value else ""
    text = str(remote_value or item).lower()
    return "Remote" if "remote" in text else ""
