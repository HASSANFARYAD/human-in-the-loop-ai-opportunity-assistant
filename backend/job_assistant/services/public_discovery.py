"""
Auto-discovery source adapters.

Each ``fetch_*`` function polls a public, no-login job board API
(RemoteJobs.org, Arbeitnow, Remotive, Jobicy, Hacker News "Who is
hiring?", RemoteOK, The Muse) and returns normalised opportunity dicts.
``discover_public_opportunities`` aggregates selected sources and
deduplicates the combined pool.

These are *auto-discovered* sources — they run on a schedule or on
demand via the discovery endpoint.  They are distinct from:

* **Manual import** (``job_import.py``) — CSV uploads, URL paste-in,
  and the structured form entry (title + company + description, no
  URL required).
* **Scraper sources** (``job_source_scrapers.py``) — per-user scrapers
  that need an explicit URL to start from (e.g. an Indeed search page).

All three paths converge on ``import_opportunities()`` in
``job_import.py``, which runs the same dedup pipeline and inserts into
the database.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List
from urllib.parse import urlencode

import requests


DEFAULT_TIMEOUT_SECONDS = 15


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value)


def _clean_html(value: Any) -> str:
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(_text(value), "html.parser").get_text(" ", strip=True)
    except ModuleNotFoundError:
        import re

        return re.sub(r"<[^>]+>", " ", _text(value)).strip()


def _matches_query(opportunity: Dict[str, Any], query: str) -> bool:
    if not query.strip():
        return True
    haystack = " ".join(
        _text(opportunity.get(key))
        for key in ["title", "company", "location", "description", "raw_text"]
    ).lower()
    return all(term.lower() in haystack for term in query.split())


def _content_hash(job: Dict[str, Any]) -> str:
    raw = "|".join([
        str(job.get("title") or "").strip().lower(),
        str(job.get("company") or "").strip().lower(),
        str(job.get("description") or job.get("raw_text") or "").strip().lower(),
    ])
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dedupe(opportunities: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from job_assistant.db import _fuzzy_match_title_company
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    seen_tc: set[str] = set()
    seen_fuzzy: list[tuple[str, str]] = []
    unique: list[dict[str, Any]] = []
    for opportunity in opportunities:
        url = opportunity.get("url") or ""
        title = str(opportunity.get("title") or "").strip()
        company = str(opportunity.get("company") or "").strip()
        ch = _content_hash(opportunity)
        tc_key = f"{title}|{company}" if title and company else ""
        if url and url in seen_urls:
            continue
        if ch in seen_hashes:
            continue
        if tc_key and tc_key in seen_tc:
            continue
        if title and company and _fuzzy_match_title_company(title, company, seen_fuzzy):
            continue
        seen_urls.add(url) if url else None
        seen_hashes.add(ch)
        if tc_key:
            seen_tc.add(tc_key)
        if title and company:
            seen_fuzzy.append((title, company))
        unique.append(opportunity)
    return unique


def _freshness_filter(
    opportunities: List[Dict[str, Any]],
    max_age_days: int | None,
) -> List[Dict[str, Any]]:
    if max_age_days is None or max_age_days <= 0:
        return opportunities
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    filtered: list[dict[str, Any]] = []
    for item in opportunities:
        date_str = item.get("date_received") or ""
        if not date_str:
            filtered.append(item)
            continue
        try:
            item_date = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            filtered.append(item)
            continue
        if item_date >= cutoff:
            filtered.append(item)
    return filtered


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


def fetch_remoteok(
    query: str = "",
    limit: int = 20,
    location: str = "",
    min_salary: int = 0,
) -> List[Dict[str, Any]]:
    url = "https://remoteok.com/api"
    response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()

    raw_tags = [t.strip().lower() for t in query.replace("+", " ").split()] if query.strip() else []
    loc_filter = location.strip().lower() if location else ""

    opportunities: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict) or not row.get("id") or not row.get("position"):
            continue

        pos = (row.get("position") or "").lower()
        comp = (row.get("company") or "").lower()
        desc = (row.get("description") or "").lower()
        tags = " ".join(row.get("tags") or []).lower()

        if raw_tags:
            if not all(
                t in pos or t in comp or t in desc or t in tags
                for t in raw_tags
            ):
                continue

        if loc_filter and loc_filter not in (row.get("location") or "").lower():
            continue

        sal_min = row.get("salary_min") or 0
        sal_max = row.get("salary_max") or 0
        if min_salary and sal_min and sal_max:
            if sal_max < min_salary:
                continue
        elif min_salary and sal_min and sal_min < min_salary:
            continue

        slug = row.get("slug", "")
        opportunities.append(
            {
                "title": row.get("position") or "Untitled remote job",
                "company": row.get("company", ""),
                "location": row.get("location", "Remote"),
                "remote_type": "Remote",
                "url": f"https://remoteok.com/remote-jobs/{slug}" if slug else "",
                "source": "RemoteOK",
                "date_received": _text(row.get("date"))[:10],
                "description": _clean_html(row.get("description", "")),
                "salary_min": sal_min if sal_min else None,
                "salary_max": sal_max if sal_max else None,
                "deadline": "",
                "opportunity_type": "job",
                "raw_text": ", ".join(row.get("tags", [])),
            }
        )
        if len(opportunities) >= limit:
            break
    return opportunities


def fetch_muse(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    params: dict[str, Any] = {"page": 1, "descending": "true"}
    if query.strip():
        params["query"] = query.strip()
    url = f"https://www.themuse.com/api/public/jobs?{urlencode(params)}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()

    opportunities: list[dict[str, Any]] = []
    for row in data.get("results", []):
        company = row.get("company") or {}
        locations = row.get("locations") or []
        location = locations[0].get("name", "") if locations else ""
        opportunities.append(
            {
                "title": row.get("name") or "Untitled job",
                "company": company.get("name", "") if isinstance(company, dict) else str(company),
                "location": location,
                "remote_type": "",
                "url": (row.get("refs") or {}).get("landing_page", ""),
                "source": "The Muse",
                "date_received": _text(row.get("publication_date"))[:10],
                "description": _clean_html(row.get("contents", "")),
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
    max_age_days: int | None = None,
) -> List[Dict[str, Any]]:
    selected = set(sources or ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring", "RemoteOK", "The Muse"])
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
    if "RemoteOK" in selected:
        found.extend(fetch_remoteok(query=query, limit=limit_per_source))
    if "The Muse" in selected:
        found.extend(fetch_muse(query=query, limit=limit_per_source))
    deduped = _dedupe(found)
    return _freshness_filter(deduped, max_age_days)
