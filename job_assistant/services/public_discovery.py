from __future__ import annotations

from typing import Any, Dict, Iterable, List
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


DEFAULT_TIMEOUT_SECONDS = 15


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value)


def _clean_html(value: Any) -> str:
    return BeautifulSoup(_text(value), "html.parser").get_text(" ", strip=True)


def _matches_query(opportunity: Dict[str, Any], query: str) -> bool:
    if not query.strip():
        return True
    haystack = " ".join(
        _text(opportunity.get(key))
        for key in ["title", "company", "location", "description", "raw_text"]
    ).lower()
    return all(term.lower() in haystack for term in query.split())


def _dedupe(opportunities: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for opportunity in opportunities:
        key = opportunity.get("url") or f"{opportunity.get('title')}|{opportunity.get('company')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(opportunity)
    return unique


def fetch_remotejobs(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
    if query.strip():
        params["q"] = query.strip()
    url = f"https://remotejobs.org/api/v1/jobs?{urlencode(params)}"
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    rows = data.get("data", data if isinstance(data, list) else [])

    opportunities: list[dict[str, Any]] = []
    for row in rows:
        company = row.get("company") or {}
        opportunities.append(
            {
                "title": row.get("title") or "Untitled remote job",
                "company": company.get("name", "") if isinstance(company, dict) else _text(company),
                "location": row.get("location", "Remote"),
                "remote_type": "Remote",
                "url": row.get("apply_url") or row.get("url") or "",
                "source": "RemoteJobs.org",
                "date_received": _text(row.get("posted_at"))[:10],
                "description": row.get("description", ""),
                "salary_min": row.get("salary_min"),
                "salary_max": row.get("salary_max"),
                "deadline": "",
                "opportunity_type": "job",
                "raw_text": _text(row),
            }
        )
    return opportunities


def fetch_arbeitnow(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    response = requests.get("https://arbeitnow.com/api/job-board-api", timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    rows = data.get("data", data if isinstance(data, list) else [])

    opportunities: list[dict[str, Any]] = []
    for row in rows:
        opportunity = {
            "title": row.get("title") or "Untitled job",
            "company": row.get("company_name", ""),
            "location": row.get("location", ""),
            "remote_type": "Remote" if row.get("remote") else "",
            "url": row.get("url") or row.get("slug") or "",
            "source": "Arbeitnow",
            "date_received": _text(row.get("created_at") or row.get("date"))[:10],
            "description": row.get("description") or _text(row.get("tags")),
            "salary_min": None,
            "salary_max": None,
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": _text(row),
        }
        if _matches_query(opportunity, query):
            opportunities.append(opportunity)
        if len(opportunities) >= limit:
            break
    return opportunities


def fetch_remotive(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    params: dict[str, Any] = {"limit": max(1, min(limit, 100))}
    if query.strip():
        params["search"] = query.strip()
    url = f"https://remotive.com/api/remote-jobs?{urlencode(params)}"
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()

    opportunities: list[dict[str, Any]] = []
    for row in data.get("jobs", []):
        opportunities.append(
            {
                "title": row.get("title") or "Untitled remote job",
                "company": row.get("company_name", ""),
                "location": row.get("candidate_required_location", "Remote"),
                "remote_type": "Remote",
                "url": row.get("url", ""),
                "source": "Remotive",
                "date_received": _text(row.get("publication_date"))[:10],
                "description": _clean_html(row.get("description", "")),
                "salary_min": None,
                "salary_max": None,
                "deadline": "",
                "opportunity_type": "job",
                "raw_text": _text(row),
            }
        )
    return opportunities


def fetch_jobicy(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    params: dict[str, Any] = {"count": max(1, min(limit, 100))}
    if query.strip():
        params["tag"] = query.strip()
    url = f"https://jobicy.com/api/v2/remote-jobs?{urlencode(params)}"
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    rows = data.get("jobs", data if isinstance(data, list) else [])

    opportunities: list[dict[str, Any]] = []
    for row in rows:
        opportunities.append(
            {
                "title": row.get("jobTitle") or "Untitled remote job",
                "company": row.get("companyName", ""),
                "location": row.get("jobGeo", "Remote"),
                "remote_type": "Remote",
                "url": row.get("url", ""),
                "source": "Jobicy",
                "date_received": _text(row.get("pubDate"))[:10],
                "description": _clean_html(row.get("jobDescription") or row.get("jobExcerpt", "")),
                "salary_min": row.get("salaryMin"),
                "salary_max": row.get("salaryMax"),
                "deadline": "",
                "opportunity_type": "job",
                "raw_text": _text(row),
            }
        )
    return opportunities


def fetch_hackernews_who_is_hiring(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    thread_params = {
        "query": "Ask HN: Who is hiring?",
        "tags": "story",
        "hitsPerPage": 5,
    }
    thread_url = f"https://hn.algolia.com/api/v1/search_by_date?{urlencode(thread_params)}"
    thread_response = requests.get(thread_url, timeout=DEFAULT_TIMEOUT_SECONDS)
    thread_response.raise_for_status()
    threads = thread_response.json().get("hits", [])
    thread = next((item for item in threads if "who is hiring" in _text(item.get("title")).lower()), None)
    if not thread:
        return []

    story_id = thread.get("objectID")
    comment_params = {
        "tags": f"comment,story_{story_id}",
        "hitsPerPage": max(1, min(limit * 3, 100)),
    }
    if query.strip():
        comment_params["query"] = query.strip()
    comment_url = f"https://hn.algolia.com/api/v1/search_by_date?{urlencode(comment_params)}"
    comment_response = requests.get(comment_url, timeout=DEFAULT_TIMEOUT_SECONDS)
    comment_response.raise_for_status()

    opportunities: list[dict[str, Any]] = []
    for row in comment_response.json().get("hits", []):
        description = _clean_html(row.get("comment_text", ""))
        if not description:
            continue
        title = description.split(".")[0][:120] or "Hacker News hiring post"
        opportunities.append(
            {
                "title": title,
                "company": "",
                "location": "",
                "remote_type": "Remote" if "remote" in description.lower() else "",
                "url": f"https://news.ycombinator.com/item?id={row.get('objectID')}",
                "source": "Hacker News Who is hiring",
                "date_received": _text(row.get("created_at"))[:10],
                "description": description,
                "salary_min": None,
                "salary_max": None,
                "deadline": "",
                "opportunity_type": "job",
                "raw_text": _text(row),
            }
        )
        if len(opportunities) >= limit:
            break
    return opportunities


def discover_public_opportunities(
    query: str = "",
    sources: Iterable[str] | None = None,
    limit_per_source: int = 20,
) -> List[Dict[str, Any]]:
    selected = set(sources or ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"])
    found: list[dict[str, Any]] = []
    if "RemoteJobs.org" in selected:
        found.extend(fetch_remotejobs(query=query, limit=limit_per_source))
    if "Arbeitnow" in selected:
        found.extend(fetch_arbeitnow(query=query, limit=limit_per_source))
    if "Remotive" in selected:
        found.extend(fetch_remotive(query=query, limit=limit_per_source))
    if "Jobicy" in selected:
        found.extend(fetch_jobicy(query=query, limit=limit_per_source))
    if "Hacker News Who is hiring" in selected:
        found.extend(fetch_hackernews_who_is_hiring(query=query, limit=limit_per_source))
    return _dedupe(found)
