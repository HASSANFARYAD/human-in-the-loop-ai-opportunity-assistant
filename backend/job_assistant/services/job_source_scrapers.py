"""
Job-source scrapers — per-user, URL-driven discovery.

Each scraper subclass of ``JobSourceScraper`` requires an explicit URL
or source hint to begin (e.g. an Indeed search-result page).  They are
configured per-user and run on demand.  This is unlike
``public_discovery.py``, which polls public job-board APIs without user
configuration.

All scrapers converge with auto-discovered and manually-entered jobs
in ``import_opportunities()``, which runs the same dedup pipeline.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


DEFAULT_PAGE_LIMIT = 2
DEFAULT_TIMEOUT_SECONDS = 20


class ScraperError(RuntimeError):
    """Raised when a source scraper cannot fetch or parse a listing page."""


class UnsupportedSourceUrl(ValueError):
    """Raised when no scraper supports a URL."""


@dataclass
class ScrapeResult:
    source: str
    requested_url: str
    page_urls: list[str] = field(default_factory=list)
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def found_count(self) -> int:
        return len(self.opportunities)


class JobSourceScraper(ABC):
    source_name: str

    @abstractmethod
    def supports(self, url: str, source: str = "") -> bool:
        raise NotImplementedError

    @abstractmethod
    def scrape(self, url: str, page_limit: int = DEFAULT_PAGE_LIMIT) -> ScrapeResult:
        raise NotImplementedError


class IndeedScraper(JobSourceScraper):
    source_name = "Indeed"

    def __init__(self, fetch: Callable[[str], str] | None = None) -> None:
        self._fetch = fetch or self._fetch_url

    def supports(self, url: str, source: str = "") -> bool:
        parsed = urlparse(url.strip())
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        source_matches = source.strip().lower() in {"", "indeed", "manual", "other"}
        return source_matches and host.endswith("indeed.com") and (
            path.rstrip("/") == "/jobs"
            or path.startswith("/q-")
            or "/jobs/search" in path
            or "/jobs/collections" in path
        )

    def scrape(self, url: str, page_limit: int = DEFAULT_PAGE_LIMIT) -> ScrapeResult:
        page_urls = indeed_page_urls(url, max(1, min(page_limit, DEFAULT_PAGE_LIMIT)))
        result = ScrapeResult(source=self.source_name, requested_url=url, page_urls=page_urls)
        for page_url in page_urls:
            try:
                html = self._fetch(page_url)
                jobs = self._parse_page(html, page_url)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                raise ScraperError(f"Indeed page fetch failed with status {status}") from exc
            except requests.RequestException as exc:
                raise ScraperError(f"Indeed page fetch failed: {exc}") from exc
            except Exception as exc:
                raise ScraperError(f"Indeed page parse failed: {exc}") from exc
            if not jobs:
                result.warnings.append(f"No jobs parsed from {page_url}")
            result.opportunities.extend(jobs)
        result.opportunities = _dedupe_opportunities(result.opportunities)
        return result

    def _fetch_url(self, url: str) -> str:
        response = requests.get(
            url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; JobAssistantBot/1.0; +https://example.com)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        response.raise_for_status()
        text = response.text or ""
        if _looks_blocked(text):
            raise ScraperError("Indeed page appears blocked or unavailable")
        return text

    def _parse_page(self, html: str, page_url: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html or "", "html.parser")
        jobs = _parse_next_data_jobs(soup, page_url)
        if not jobs:
            jobs = _parse_indeed_cards(soup, page_url)
        return jobs


def is_job_listing_url(raw: str) -> bool:
    if not raw or not raw.strip().lower().startswith(("http://", "https://")):
        return False
    parsed = urlparse(raw.strip())
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return host.endswith("indeed.com") and (
        path.rstrip("/") == "/jobs"
        or path.startswith("/q-")
        or "/jobs/search" in path
        or "/jobs/collections" in path
    )


def get_scraper_for_url(url: str, source: str = "") -> JobSourceScraper:
    scrapers: list[JobSourceScraper] = [IndeedScraper()]
    for scraper in scrapers:
        if scraper.supports(url, source):
            return scraper
    raise UnsupportedSourceUrl("Unsupported source URL. Currently direct URL scraping supports Indeed search result URLs.")


def indeed_page_urls(url: str, page_limit: int = DEFAULT_PAGE_LIMIT) -> list[str]:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid URL")
    limit = max(1, min(page_limit, DEFAULT_PAGE_LIMIT))
    query = parse_qs(parsed.query, keep_blank_values=True)
    urls: list[str] = []
    for page in range(limit):
        next_query = {key: list(value) for key, value in query.items()}
        if page == 0:
            next_query.pop("start", None)
        else:
            next_query["start"] = [str(page * 10)]
        encoded = urlencode(next_query, doseq=True)
        urls.append(urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/jobs", parsed.params, encoded, "")))
    return urls


def indeed_url_with_work_location_intent(url: str, work_location_filter: str = "all") -> str:
    if work_location_filter != "remote":
        return url
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    existing_intent = " ".join(" ".join(values) for key, values in query.items() if key.lower() in {"q", "l", "remotejob", "sc"}).lower()
    if any(marker in existing_intent for marker in ["remote", "work from home", "wfh", "anywhere"]):
        return url
    q_values = query.get("q") or [""]
    base_query = q_values[0].strip()
    query["q"] = [f"{base_query} remote".strip()]
    encoded = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/jobs", parsed.params, encoded, parsed.fragment))


def _parse_next_data_jobs(soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
    script = soup.find("script", id="mosaic-data") or soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return []
    rows = list(_walk_job_dicts(data))
    return [_normalize_indeed_row(row, page_url) for row in rows if _normalize_indeed_row(row, page_url)]


def _walk_job_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        keys = set(value)
        if {"title", "company"}.issubset(keys) or "jobkey" in keys or "jobKey" in keys:
            found.append(value)
        for child in value.values():
            found.extend(_walk_job_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_job_dicts(child))
    return found


def _parse_indeed_cards(soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
    cards = soup.select("[data-jk], .job_seen_beacon, .jobsearch-SerpJobCard")
    jobs: list[dict[str, Any]] = []
    for card in cards:
        title_attr_el = card.select_one("h2 a span[title], span[title]")
        title_el = title_attr_el or card.select_one("h2 a, [data-testid='jobTitle'], .jobTitle")
        company_el = card.select_one("[data-testid='company-name'], .companyName, .company")
        location_el = card.select_one("[data-testid='text-location'], .companyLocation, .location")
        salary_el = card.select_one("[data-testid='attribute_snippet_testid'], .salary-snippet-container, .salaryText")
        date_el = card.select_one("[data-testid='myJobsStateDate'], .date")
        snippet_el = card.select_one(".job-snippet, [data-testid='job-snippet'], .summary")
        link_el = card.select_one("h2 a[href], a[href*='/rc/clk'], a[href*='/pagead/clk']")
        jobkey = card.get("data-jk") or _query_value(link_el.get("href", "") if link_el else "", "jk") or _query_value(page_url, "vjk")
        title = _clean(title_attr_el.get("title") if title_attr_el else title_el.get_text(" ", strip=True) if title_el else "")
        if not title:
            continue
        href = link_el.get("href", "") if link_el else ""
        jobs.append(
            {
                "title": title,
                "company": _clean(company_el.get_text(" ", strip=True) if company_el else ""),
                "location": _clean(location_el.get_text(" ", strip=True) if location_el else ""),
                "remote_type": "Remote" if "remote" in _clean(location_el.get_text(" ", strip=True) if location_el else "").lower() else "",
                "url": _indeed_job_url(href, page_url, jobkey),
                "source": "Indeed",
                "date_received": datetime.now(timezone.utc).date().isoformat(),
                "description": _clean(snippet_el.get_text(" ", strip=True) if snippet_el else ""),
                "salary_min": None,
                "salary_max": None,
                "deadline": "",
                "opportunity_type": "job",
                "raw_text": json.dumps(
                    {
                        "jobkey": jobkey,
                        "salary": _clean(salary_el.get_text(" ", strip=True) if salary_el else ""),
                        "posted_date": _clean(date_el.get_text(" ", strip=True) if date_el else ""),
                        "job_type": _extract_job_type(card.get_text(" ", strip=True)),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    return jobs


def _normalize_indeed_row(row: dict[str, Any], page_url: str) -> dict[str, Any] | None:
    title = _first(row, ["title", "jobTitle", "displayTitle", "normTitle"])
    if not title:
        return None
    company = row.get("company") if isinstance(row.get("company"), dict) else {}
    location = row.get("formattedLocation") or row.get("location") or row.get("jobLocation")
    jobkey = _first(row, ["jobkey", "jobKey", "key", "jobId", "id"]) or _query_value(page_url, "vjk")
    description = _first(row, ["snippet", "summary", "description", "jobDescription"])
    return {
        "title": title,
        "company": _first(row, ["companyName", "company"]) or _first(company, ["name", "displayName"]),
        "location": _clean(location),
        "remote_type": "Remote" if "remote" in f"{location} {description}".lower() else "",
        "url": _indeed_job_url(_first(row, ["url", "jobUrl", "link"]), page_url, jobkey),
        "source": "Indeed",
        "date_received": _first(row, ["formattedRelativeTime", "pubDate", "date"]) or datetime.now(timezone.utc).date().isoformat(),
        "description": description,
        "salary_min": None,
        "salary_max": None,
        "deadline": "",
        "opportunity_type": "job",
        "raw_text": json.dumps(row, ensure_ascii=False),
    }


def _first(item: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        text = _clean(str(value))
        if text:
            return text
    return ""


def _indeed_job_url(href: str, page_url: str, jobkey: str = "") -> str:
    if href:
        absolute = urljoin(page_url, href)
        if urlparse(absolute).netloc:
            return absolute
    parsed = urlparse(page_url)
    if jobkey:
        return f"{parsed.scheme}://{parsed.netloc}/viewjob?jk={jobkey}"
    return page_url


def _query_value(url: str, key: str) -> str:
    return (parse_qs(urlparse(url).query).get(key) or [""])[0]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_job_type(text: str) -> str:
    for job_type in ["Full-time", "Part-time", "Contract", "Temporary", "Internship"]:
        if job_type.lower() in text.lower():
            return job_type
    return ""


def _content_hash(job: dict[str, Any]) -> str:
    import hashlib
    raw = "|".join([
        str(job.get("title") or "").strip().lower(),
        str(job.get("company") or "").strip().lower(),
        str(job.get("description") or job.get("raw_text") or "").strip().lower(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dedupe_opportunities(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    seen_tc: set[str] = set()
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
        seen_urls.add(url) if url else None
        seen_hashes.add(ch)
        if tc_key:
            seen_tc.add(tc_key)
        unique.append(opportunity)
    return unique


def _looks_blocked(html: str) -> bool:
    text = html[:5000].lower()
    return any(marker in text for marker in ["captcha", "verify you are human", "access denied", "blocked"])
