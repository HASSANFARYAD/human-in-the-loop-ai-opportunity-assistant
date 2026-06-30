from __future__ import annotations

import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from job_assistant.db import insert_job, _fuzzy_match_title_company, _content_hash

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
SOURCE_TIMEOUT = 45
CIRCUIT_MAX_FAILURES = 3
CIRCUIT_COOLDOWN_SECONDS = 300

_circuit_lock = threading.Lock()
_circuit_state: dict[str, dict[str, Any]] = {}


class CircuitBreaker:
    """Per-source circuit breaker with consecutive-failure tracking and cooldown."""

    def __init__(self, max_failures: int = CIRCUIT_MAX_FAILURES,
                 cooldown: int = CIRCUIT_COOLDOWN_SECONDS) -> None:
        self.max_failures = max_failures
        self.cooldown = cooldown

    def _ensure(self, name: str) -> dict[str, Any]:
        with _circuit_lock:
            if name not in _circuit_state:
                _circuit_state[name] = {
                    "failures": 0,
                    "open_until": 0.0,
                    "last_error": "",
                }
            return _circuit_state[name]

    def allow(self, name: str) -> bool:
        state = self._ensure(name)
        with _circuit_lock:
            if state["open_until"] > 0:
                if state["open_until"] > datetime.now().timestamp():
                    logger.warning("Circuit breaker open for %s (cooldown %.0fs remaining)",
                                   name, state["open_until"] - datetime.now().timestamp())
                    return False
                state["failures"] = 0
                state["open_until"] = 0
        return True

    def record_success(self, name: str) -> None:
        state = self._ensure(name)
        with _circuit_lock:
            state["failures"] = 0
            state["open_until"] = 0
            state["last_error"] = ""

    def record_failure(self, name: str, error: str) -> None:
        state = self._ensure(name)
        with _circuit_lock:
            state["failures"] += 1
            state["last_error"] = error
            if state["failures"] >= self.max_failures:
                state["open_until"] = datetime.now().timestamp() + self.cooldown
                logger.error("Circuit breaker OPEN for %s after %d failures (cooldown %ss): %s",
                             name, state["failures"], self.cooldown, error)

    def stats(self, name: str) -> dict[str, Any]:
        state = self._ensure(name)
        with _circuit_lock:
            is_open = state["open_until"] > datetime.now().timestamp()
            return {
                "source": name,
                "consecutive_failures": state["failures"],
                "circuit_open": is_open,
                "cooldown_remaining": max(0.0, state["open_until"] - datetime.now().timestamp()) if is_open else 0.0,
                "last_error": state["last_error"],
            }

    def reset(self, name: str) -> None:
        with _circuit_lock:
            _circuit_state.pop(name, None)


circuit_breaker = CircuitBreaker()


def _fetch_source_with_timeout(
    name: str, fetcher: Any, query: str, limit: int,
) -> list[dict[str, Any]]:
    if not circuit_breaker.allow(name):
        return []

    def _run() -> list[dict[str, Any]]:
        return fetcher(query=query, limit=limit)

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_run)
        try:
            items = fut.result(timeout=SOURCE_TIMEOUT)
            circuit_breaker.record_success(name)
            logger.info("Fetched %d jobs from %s", len(items), name)
            return items
        except FuturesTimeout:
            circuit_breaker.record_failure(name, f"timeout after {SOURCE_TIMEOUT}s")
            logger.error("Timeout fetching from %s (%ss)", name, SOURCE_TIMEOUT)
            return []
        except Exception as e:
            circuit_breaker.record_failure(name, str(e))
            logger.error("Failed to fetch from %s: %s", name, e)
            return []
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SOURCE_NAMES = [
    "USAJobs",
    "Reed.co.uk",
    "Coroflot",
    "GulfTalent",
    "Naukri",
    "Zippia",
    "Xing",
    "NaukriGulf",
    "WizeHire",
    "MyCariera",
    "Linq",
    "CareerAddict",
    "iRecruitee",
    "InstaHyre",
    "Skywalker",
    "WhatJobs",
    "CareerPage",
]


def _headers(referer: str = "") -> dict[str, str]:
    h = {"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"}
    if referer:
        h["Referer"] = referer
    return h


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value)


def _clean_html(value: Any) -> str:
    return BeautifulSoup(_text(value), "html.parser").get_text(" ", strip=True)


def _dedupe_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    seen_tc: set[str] = set()
    seen_fuzzy: list[tuple[str, str]] = []
    unique: list[dict[str, Any]] = []
    for item in items:
        url = item.get("url") or ""
        title = str(item.get("title") or "").strip()
        company = str(item.get("company") or "").strip()
        ch = _content_hash(item)
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
        unique.append(item)
    return unique


def _soup(url: str, params: dict | None = None) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, params=params, headers=_headers(url), timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def _json_get(url: str, params: dict | None = None, headers: dict | None = None) -> list | dict | None:
    try:
        h = _headers(url)
        if headers:
            h.update(headers)
        resp = requests.get(url, params=params, headers=h, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Failed to GET %s: %s", url, e)
        return None


# ── USAJobs (official API, free) ──────────────────────────────────────────


def fetch_usajobs(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    api_key = os.environ.get("USAJOBS_API_KEY", "").strip()
    if not api_key:
        logger.warning("USAJobs API key not set — set USAJOBS_API_KEY env var")
        return []
    url = "https://data.usajobs.gov/api/search"
    params: dict[str, Any] = {"ResultsPerPage": min(limit, 100), "Page": 1}
    if query.strip():
        params["Keyword"] = query.strip()
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": USER_AGENT,
        "Authorization-Key": api_key,
    }
    data = _json_get(url, params, headers)
    if not data or not isinstance(data, dict):
        return []
    results = data.get("SearchResult", {}).get("SearchResultItems", [])
    opportunities = []
    for item in results:
        row = item.get("MatchedObjectDescriptor", {})
        pos = row.get("PositionLocation", [{}])[0] if row.get("PositionLocation") else {}
        loc_parts = [pos.get("City", ""), pos.get("CountryName", "")]
        opportunities.append({
            "title": row.get("PositionTitle", "Untitled"),
            "company": "USAJobs",
            "location": ", ".join(p for p in loc_parts if p),
            "remote_type": "Remote" if row.get("PositionRemoteIndicator") == "Yes" else "",
            "url": row.get("PositionURI", ""),
            "source": "USAJobs",
            "date_received": (row.get("PublicationStartDate") or "")[:10],
            "description": _clean_html(row.get("JobSummary", "")),
            "salary_min": str(row.get("PositionRemuneration", [{}])[0].get("MinimumRange", "")) if row.get("PositionRemuneration") else "",
            "salary_max": str(row.get("PositionRemuneration", [{}])[0].get("MaximumRange", "")) if row.get("PositionRemuneration") else "",
            "deadline": (row.get("ApplicationCloseDate") or "")[:10],
            "opportunity_type": "job",
            "raw_text": json.dumps(row, ensure_ascii=False),
        })
    return opportunities[:limit]


# ── Reed.co.uk (UK, has REST API) ─────────────────────────────────────────


def fetch_reed(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.reed.co.uk/api/1.0/search"
    params: dict[str, Any] = {"resultsToTake": min(limit, 100)}
    if query.strip():
        params["keywords"] = query.strip()
    from requests.auth import HTTPBasicAuth
    try:
        resp = requests.get(url, params=params, auth=HTTPBasicAuth("", ""), headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Reed API failed: %s", e)
        return []
    results = data.get("results", []) if isinstance(data, dict) else []
    opportunities = []
    for row in results:
        opp = {
            "title": row.get("jobTitle", "Untitled"),
            "company": row.get("employerName", ""),
            "location": row.get("locationName", ""),
            "remote_type": "Remote" if row.get("isRemote") else "",
            "url": row.get("jobUrl", ""),
            "source": "Reed.co.uk",
            "date_received": (row.get("datePosted") or "")[:10],
            "description": _clean_html(row.get("jobDescription", "")),
            "salary_min": str(row.get("minimumSalary", "")),
            "salary_max": str(row.get("maximumSalary", "")),
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": json.dumps(row, ensure_ascii=False),
        }
        opportunities.append(opp)
    return opportunities[:limit]


# ── Coroflot (creative/design jobs, scrape) ───────────────────────────────


def fetch_coroflot(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.coroflot.com/jobs"
    params = {"q": query.strip() or "design", "sort": "date"}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div.job-listing, article.job-card, div[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title'], a[class*='job']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.coroflot.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "Coroflot",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── GulfTalent (Middle East, scrape) ──────────────────────────────────────


def fetch_gulftalent(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.gulftalent.com/jobs"
    params = {"keywords": query.strip() or "software", "page": 1}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div.job-item, article.job-card, div[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.gulftalent.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "GulfTalent",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── Naukri (India, scrape) ────────────────────────────────────────────────


def fetch_naukri(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.naukri.com/job-listings"
    params: dict[str, Any] = {}
    if query.strip():
        params["search"] = query.strip()
    params["sort"] = "date"
    soup = _soup("https://www.naukri.com", params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("article.jobTuple, div[class*='jobTuple'], div[class*='job-card']")[:limit]
    for card in cards:
        title_el = card.select_one("a.title, a[class*='title']")
        company_el = card.select_one("a[class*='company'], div[class*='company-name']")
        loc_el = card.select_one("span[class*='location'], li[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.naukri.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "Naukri",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── Zippia (US aggregator, scrape) ────────────────────────────────────────


def fetch_zippia(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.zippia.com/jobs"
    params = {"q": query.strip() or "software engineer"}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div.job-card, article[class*='job'], div[class*='job-listing']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.zippia.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "Zippia",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── Xing (Germany, has API) ────────────────────────────────────────────────


def fetch_xing(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.xing.com/jobs/search"
    params = {"keywords": query.strip() or "software engineer", "page": 1}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("a[class*='title'], h2 a, h3 a")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.xing.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "Xing",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── NaukriGulf (Middle East, scrape) ──────────────────────────────────────


def fetch_naukrigulf(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.naukrigulf.com/jobs"
    params = {"keywords": query.strip() or "software engineer"}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("article.jobTuple, div[class*='jobTuple'], div[class*='job-card']")[:limit]
    for card in cards:
        title_el = card.select_one("a.title, a[class*='title']")
        company_el = card.select_one("a[class*='company-name'], span[class*='company']")
        loc_el = card.select_one("span[class*='location'], li[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.naukrigulf.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "NaukriGulf",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── WizeHire (US SMB, scrape) ─────────────────────────────────────────────


def fetch_wizehire(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.wizehire.com/jobs"
    params = {"q": query.strip() or ""}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job-card'], article[class*='job'], div[class*='listing']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.wizehire.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "WizeHire",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── MyCariera (Middle East, scrape) ───────────────────────────────────────


def fetch_mycariera(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.mycariera.com/jobs"
    params = {"q": query.strip() or "software"}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.mycariera.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "MyCariera",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── Linq (scrape) ─────────────────────────────────────────────────────────


def fetch_linq(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://linq.com/jobs"
    params = {"q": query.strip() or ""}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "Linq",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── CareerAddict (scrape) ─────────────────────────────────────────────────


def fetch_careeraddict(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.careeraddict.com/jobs"
    params = {"q": query.strip() or ""}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.careeraddict.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": "",
            "remote_type": "",
            "url": link,
            "source": "CareerAddict",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── iRecruitee (scrape) ───────────────────────────────────────────────────


def fetch_irecruitee(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://irecruitee.com/jobs"
    params = {"q": query.strip() or ""}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://irecruitee.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": "",
            "remote_type": "",
            "url": link,
            "source": "iRecruitee",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── InstaHyre (India, scrape) ─────────────────────────────────────────────


def fetch_instahyre(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.instahyre.com/jobs"
    params = {"q": query.strip() or "software engineer"}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.instahyre.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "InstaHyre",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── Skywalker (scrape) ────────────────────────────────────────────────────


def fetch_skywalker(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://skywalker.com/jobs"
    params = {"q": query.strip() or ""}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://skywalker.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": "",
            "remote_type": "",
            "url": link,
            "source": "Skywalker",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── WhatJobs (aggregator, scrape) ─────────────────────────────────────────


def fetch_whatjobs(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    url = "https://www.whatjobs.com/jobs"
    params = {"q": query.strip() or ""}
    soup = _soup(url, params)
    if not soup:
        return []
    opportunities = []
    cards = soup.select("div[class*='job'], article[class*='job']")[:limit]
    for card in cards:
        title_el = card.select_one("h2 a, h3 a, a[class*='title']")
        company_el = card.select_one("span[class*='company'], div[class*='company']")
        loc_el = card.select_one("span[class*='location'], div[class*='location']")
        link = title_el.get("href", "") if title_el else ""
        if link and not link.startswith("http"):
            link = "https://www.whatjobs.com" + link
        opportunities.append({
            "title": _text(title_el.get_text(strip=True) if title_el else "Untitled"),
            "company": _text(company_el.get_text(strip=True) if company_el else ""),
            "location": _text(loc_el.get_text(strip=True) if loc_el else ""),
            "remote_type": "",
            "url": link,
            "source": "WhatJobs",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": card.get_text(" ", strip=True),
        })
    return opportunities[:limit]


# ── Generic career page scraping ──────────────────────────────────────────


def fetch_career_page(url: str) -> list[dict[str, Any]]:
    soup = _soup(url)
    if not soup:
        return []
    opportunities = []
    for link_el in soup.select("a[href*='career'], a[href*='job'], a[href*='vacancy']"):
        href = link_el.get("href", "")
        if not href or href.startswith("#"):
            continue
        if not href.startswith("http"):
            base = "{0.scheme}://{0.netloc}".format(urlparse(url))
            href = base + href
        title = link_el.get_text(strip=True) or "Career page link"
        opportunities.append({
            "title": title,
            "company": urlparse(url).netloc.replace("www.", "").split(".")[0].title(),
            "location": "",
            "remote_type": "",
            "url": href,
            "source": "CareerPage",
            "date_received": "",
            "description": "",
            "salary_min": "",
            "salary_max": "",
            "deadline": "",
            "opportunity_type": "job",
            "raw_text": title,
        })
    return opportunities[:20]


# ── Aggregator ────────────────────────────────────────────────────────────


FETCH_MAP = {
    "USAJobs": fetch_usajobs,
    "Reed.co.uk": fetch_reed,
    "Coroflot": fetch_coroflot,
    "GulfTalent": fetch_gulftalent,
    "Naukri": fetch_naukri,
    "Zippia": fetch_zippia,
    "Xing": fetch_xing,
    "NaukriGulf": fetch_naukrigulf,
    "WizeHire": fetch_wizehire,
    "MyCariera": fetch_mycariera,
    "Linq": fetch_linq,
    "CareerAddict": fetch_careeraddict,
    "iRecruitee": fetch_irecruitee,
    "InstaHyre": fetch_instahyre,
    "Skywalker": fetch_skywalker,
    "WhatJobs": fetch_whatjobs,
}


def discover_multi_source(
    query: str = "",
    sources: list[str] | None = None,
    limit_per_source: int = 20,
) -> list[dict[str, Any]]:
    selected = set(sources or list(FETCH_MAP.keys()))
    found: list[dict[str, Any]] = []
    for name, fetcher in FETCH_MAP.items():
        if name in selected:
            items = _fetch_source_with_timeout(name, fetcher, query, limit_per_source)
            found.extend(items)
    return _dedupe_list(found)


def get_circuit_breaker_stats() -> list[dict[str, Any]]:
    stats = []
    for name in list(FETCH_MAP.keys()) + ["CareerPage"]:
        stats.append(circuit_breaker.stats(name))
    return stats


def reset_circuit_breaker(source: str | None = None) -> None:
    if source:
        circuit_breaker.reset(source)
    else:
        _circuit_state.clear()
