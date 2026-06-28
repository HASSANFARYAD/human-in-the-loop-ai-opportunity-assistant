from __future__ import annotations

import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.auth import current_user
from job_assistant.db import (
    get_integration_settings,
    get_job,
    get_profile,
    save_evaluation,
)
from job_assistant.services.apify_integration import apify_items_to_opportunities, build_run_input, run_actor_for_items
from job_assistant.services.job_import import import_opportunities
from job_assistant.services.job_source_scrapers import (
    ScraperError,
    UnsupportedSourceUrl,
    indeed_url_with_work_location_intent,
    get_scraper_for_url,
    is_job_listing_url,
)
from job_assistant.services.opportunity_classifier import (
    annotate_opportunity,
    extract_opportunities_from_container,
    is_job_like,
)
from job_assistant.services.parsing import extract_job_from_text
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.rapidapi_linkedin import search_linkedin_jobs, rapidapi_items_to_opportunities
from job_assistant.services.scoring import score_job

logger = logging.getLogger(__name__)

router = APIRouter()

WORK_LOCATION_FILTERS = {"all", "remote", "hybrid", "onsite"}
REMOTE_LOCATION_INDICATORS = ("remote", "work from home", "wfh", "anywhere")
HYBRID_LOCATION_INDICATORS = ("hybrid", "partially remote")
ONSITE_LOCATION_INDICATORS = ("onsite", "on-site", "on site", "office")


def _normalize_work_location_filter(value: Any) -> str:
    val = str(value).strip().lower() if value is not None else "all"
    if val in {"remote", "wfh", "work from home", "anywhere"}:
        return "remote"
    if val in {"hybrid", "partially remote", "partial"}:
        return "hybrid"
    if val in {"onsite", "on-site", "on site", "office", "in office", "in-office"}:
        return "onsite"
    return "all" if val in WORK_LOCATION_FILTERS else "all"


def _opportunity_location_text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(key, "")) for key in ["title", "location", "remote_type", "description"]).lower()


def _matches_work_location_filter(item: dict[str, Any], work_location_filter: str) -> bool:
    if work_location_filter == "all":
        return True
    location_text = _opportunity_location_text(item)
    if work_location_filter == "remote":
        return any(indicator in location_text for indicator in REMOTE_LOCATION_INDICATORS)
    if work_location_filter == "hybrid":
        return any(indicator in location_text for indicator in HYBRID_LOCATION_INDICATORS)
    if work_location_filter == "onsite":
        return not any(indicator in location_text for indicator in REMOTE_LOCATION_INDICATORS + HYBRID_LOCATION_INDICATORS)
    return True


def _filter_by_work_location(items: list[dict[str, Any]], work_location_filter: str) -> tuple[list[dict[str, Any]], int]:
    if work_location_filter == "all":
        return items, 0
    filtered = [item for item in items if _matches_work_location_filter(item, work_location_filter)]
    return filtered, len(items) - len(filtered)


def _url_error_detail(status: str, message: str, source: str = "") -> dict[str, str]:
    detail: dict[str, str] = {"status": status, "message": message}
    if source:
        detail["source"] = source
    return detail


def _scraper_error_response(exc: ScraperError, source: str = "") -> HTTPException:
    status_msg = "external_service_error"
    if exc.status_code == 403:
        status_msg = "blocked"
    elif exc.status_code == 404:
        status_msg = "not_found"
    return HTTPException(
        status_code=exc.status_code or 502,
        detail=_url_error_detail(status_msg, str(exc) or "External source could not be reached.", source=exc.source_name or source),
    )


def _filter_discovered_opportunities(items: list[dict[str, Any]], payload: "DiscoveryPublicIn") -> list[dict[str, Any]]:
    keywords = " ".join(part for part in [payload.query, payload.keywords, payload.country] if part).strip().lower()
    terms = [term for term in keywords.split() if term]
    filtered: list[dict[str, Any]] = []
    for item in items:
        haystack = " ".join(str(item.get(key, "")) for key in ["title", "company", "location", "remote_type", "source", "description", "raw_text"]).lower()
        if payload.opportunity_type != "auto" and item.get("opportunity_type") not in {"", None, payload.opportunity_type}:
            continue
        if payload.remote_type != "all" and payload.remote_type.lower() not in str(item.get("remote_type", "")).lower() and payload.remote_type.lower() not in haystack:
            continue
        if payload.location.strip() and payload.location.strip().lower() not in haystack:
            continue
        if terms and not all(term in haystack for term in terms):
            continue
        if payload.opportunity_type != "auto":
            item["opportunity_type"] = payload.opportunity_type
        filtered.append(item)
    return filtered


def _profile_has_resume_context(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    return any(str(profile.get(key) or "").strip() for key in ["cv_text", "skills", "target_roles", "preferred_role"])


def _profile_search_terms(profile: dict[str, Any]) -> tuple[str, list[str]]:
    role_text = str(profile.get("preferred_role") or profile.get("target_roles") or "").strip()
    skills = [part.strip() for part in re.split(r",|\n|;", str(profile.get("skills") or "")) if len(part.strip()) >= 2]
    industries = [part.strip() for part in re.split(r",|\n|;", str(profile.get("industries") or "")) if len(part.strip()) >= 2]
    fallback_resume_terms = [
        term for term in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", str(profile.get("cv_text") or ""))
        if term.lower() not in {"and", "the", "with", "for", "from", "that", "this", "resume", "experience"}
    ][:8]
    terms: list[str] = []
    if role_text:
        terms.extend(role_text.split()[:5])
    terms.extend(skills[:5])
    terms.extend(industries[:2])
    if not terms:
        terms.extend(fallback_resume_terms[:6])
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return " ".join(deduped[:8]).strip(), deduped[:12]


class DiscoveryExtractIn(BaseModel):
    workspace_id: Optional[int] = None
    raw: str
    source: str = "Manual"
    opportunity_type: str = "auto"
    work_location_filter: str = "all"

    @field_validator("work_location_filter", mode="before")
    @classmethod
    def validate_work_location_filter(cls, value: Any) -> str:
        return _normalize_work_location_filter(value)


class DiscoveryPublicIn(BaseModel):
    query: str = ""
    sources: list[str] = Field(default_factory=list)
    limit_per_source: int = 20
    opportunity_type: str = "auto"
    remote_type: str = "all"
    location: str = ""
    keywords: str = ""
    country: str = ""


class DiscoveryFromProfileIn(BaseModel):
    sources: list[str] = Field(default_factory=list)
    limit_per_source: int = 10
    save_results: bool = False
    score_results: bool = True


class DiscoveryImportIn(BaseModel):
    workspace_id: Optional[int] = None
    opportunities: list[dict[str, Any]] = Field(default_factory=list)


class DiscoveryImportUrlIn(BaseModel):
    workspace_id: Optional[int] = None
    url: str
    source: str = "Manual"
    page_limit: int = 2
    work_location_filter: str = "all"

    @field_validator("work_location_filter", mode="before")
    @classmethod
    def validate_work_location_filter(cls, value: Any) -> str:
        return _normalize_work_location_filter(value)


class ManualEntryIn(BaseModel):
    workspace_id: Optional[int] = None
    title: str = Field(..., min_length=1)
    company: str
    description: str = Field(..., min_length=1)
    url: Optional[str] = None
    location: Optional[str] = None
    remote_type: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    deadline: Optional[str] = None
    opportunity_type: str = "job"
    source: str = "Manual"


class DiscoveryRapidApiIn(BaseModel):
    workspace_id: Optional[int] = None
    title_filter: str
    location_filter: str = "United States OR United Kingdom"
    offset: int = 0


class DiscoveryApifyIn(BaseModel):
    workspace_id: Optional[int] = None
    url: str


@router.post("/discovery/extract")
async def discovery_extract(payload: DiscoveryExtractIn, user: dict = Depends(current_user)):
    if is_job_listing_url(payload.raw):
        try:
            scraper = get_scraper_for_url(payload.raw, payload.source)
            scrape_url = indeed_url_with_work_location_intent(payload.raw, payload.work_location_filter)
            scrape_result = scraper.scrape(scrape_url)
            opportunities, skipped_location = _filter_by_work_location(scrape_result.opportunities, payload.work_location_filter)
            if not opportunities:
                raise HTTPException(
                    status_code=404,
                    detail=_url_error_detail("no_content", "No usable job content was found at the provided URL.", scraper.source_name.lower()),
                )
            return {
                "status": "success", "opportunities": opportunities,
                "raw_count": scrape_result.found_count,
                "work_location_filter": payload.work_location_filter,
                "jobs_found": len(opportunities),
                "jobs_skipped_location_filter": skipped_location,
                "warnings": scrape_result.warnings,
                "message": f"Found {len(opportunities)} jobs from {scraper.source_name}. Review them before importing.",
            }
        except UnsupportedSourceUrl as exc:
            raise HTTPException(status_code=400, detail=_url_error_detail("unsupported_source", str(exc)))
        except ScraperError as exc:
            raise _scraper_error_response(exc, payload.source)
    try:
        source_classification = annotate_opportunity(
            {"title": payload.raw[:120], "description": payload.raw, "raw_text": payload.raw, "source": payload.source}
        )
        extracted = extract_opportunities_from_container(
            {"title": payload.raw[:120], "description": payload.raw, "raw_text": payload.raw, "source": payload.source}
        )
        if extracted:
            opportunities, skipped_location = _filter_by_work_location(extracted, payload.work_location_filter)
            return {
                "status": "success", "opportunities": opportunities,
                "classification": source_classification,
                "work_location_filter": payload.work_location_filter,
                "jobs_found": len(opportunities),
                "jobs_skipped_location_filter": skipped_location,
                "warnings": [] if opportunities else ["Extracted opportunities did not match the selected work-location filter."],
            }
        opportunity = extract_job_from_text(payload.raw, source=payload.source, opportunity_type=payload.opportunity_type, user_id=user["id"])
        if not opportunity.get("importable"):
            return {
                "status": "rejected", "opportunity": opportunity,
                "classification": opportunity,
                "work_location_filter": payload.work_location_filter,
                "jobs_found": 0, "jobs_skipped_location_filter": 0,
                "warnings": [opportunity.get("blocked_reason") or "No valid opportunity detected."],
            }
        opportunities, skipped_location = _filter_by_work_location([opportunity], payload.work_location_filter)
        return {
            "status": "success", "opportunity": opportunities[0] if opportunities else None,
            "classification": source_classification,
            "work_location_filter": payload.work_location_filter,
            "jobs_found": len(opportunities),
            "jobs_skipped_location_filter": skipped_location,
            "warnings": [] if opportunities else ["No extracted opportunity matched the selected work-location filter."],
        }
    except Exception as e:
        logger.error(f"Error extracting opportunity: {e}")
        raise HTTPException(status_code=500, detail="Failed to extract opportunity")


@router.post("/discovery/public")
async def discovery_public(payload: DiscoveryPublicIn, user: dict = Depends(current_user)):
    try:
        sources = payload.sources or ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"]
        opportunities = [annotate_opportunity(item) for item in discover_public_opportunities(payload.query, sources, payload.limit_per_source)]
        if payload.opportunity_type in {"auto", "job"}:
            opportunities = [item for item in opportunities if is_job_like(item)]
        return {"status": "success", "opportunities": _filter_discovered_opportunities(opportunities, payload)}
    except Exception as e:
        logger.error(f"Error discovering public opportunities: {e}")
        raise HTTPException(status_code=502, detail=f"Public discovery failed: {e}")


@router.post("/discovery/from-profile")
async def discovery_from_profile(payload: DiscoveryFromProfileIn, user: dict = Depends(current_user)):
    profile = get_profile(user["id"])
    if not _profile_has_resume_context(profile):
        raise HTTPException(status_code=400, detail="Add resume or profile details before finding jobs.")

    query, keywords = _profile_search_terms(profile or {})
    if not query:
        raise HTTPException(status_code=400, detail="No useful search terms were found in your profile.")

    sources = payload.sources or ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"]
    try:
        raw = discover_public_opportunities(query, sources, payload.limit_per_source)
    except Exception as exc:
        logger.error("Profile-based job discovery failed for user %s: %s", user["id"], exc)
        raise HTTPException(status_code=502, detail=f"Public discovery failed: {exc}")

    opportunities = [annotate_opportunity(item) for item in raw]
    opportunities = [item for item in opportunities if is_job_like(item)]
    if not opportunities:
        return {
            "status": "success", "query": query, "keywords": keywords,
            "opportunities": [], "found": 0, "imported": 0, "scored": 0,
            "using_fallback_scoring": ai_orchestrator.resolve_route(user["id"], task_type="opportunity_scoring").source == "fallback",
            "message": "No jobs were found from your profile search terms.",
        }

    using_fallback_scoring = ai_orchestrator.resolve_route(user["id"], task_type="opportunity_scoring").source == "fallback"
    scored = 0
    if payload.score_results:
        for opportunity in opportunities:
            try:
                evaluation = score_job(profile or {}, opportunity, user_id=user["id"])
                opportunity["evaluation"] = evaluation
                opportunity["match_score"] = evaluation.get("match_score")
                opportunity["score"] = evaluation.get("match_score")
                scored += 1
            except Exception as exc:
                opportunity["scoring_error"] = str(exc)
                logger.warning("Profile discovery scoring failed user_id=%s title=%s error=%s", user["id"], opportunity.get("title"), exc)
    opportunities.sort(key=lambda item: int(item.get("match_score") or -1), reverse=True)

    imported = 0
    imported_ids: list[int] = []
    warnings: list[str] = []
    errors: list[str] = []
    if payload.save_results:
        import_result = import_opportunities(opportunities, user["id"])
        imported = import_result.imported
        imported_ids = import_result.ids
        warnings = import_result.warnings
        errors = import_result.errors
        if payload.score_results and imported_ids:
            saved_jobs = [get_job(job_id, user["id"]) for job_id in imported_ids]
            for saved_job in [job for job in saved_jobs if job]:
                try:
                    evaluation = score_job(profile or {}, saved_job, user_id=user["id"])
                    save_evaluation(int(saved_job["id"]), evaluation, user["id"])
                except Exception as exc:
                    logger.warning("Profile discovery saved-job scoring failed user_id=%s job_id=%s error=%s", user["id"], saved_job.get("id"), exc)

    return {
        "status": "success" if not errors else "partial_success",
        "query": query, "keywords": keywords, "opportunities": opportunities,
        "found": len(opportunities), "imported": imported, "ids": imported_ids,
        "scored": scored,
        "using_fallback_scoring": using_fallback_scoring,
        "warnings": warnings, "errors": errors,
    }


@router.post("/discovery/rapidapi-linkedin")
async def discovery_rapidapi_linkedin(payload: DiscoveryRapidApiIn, user: dict = Depends(current_user)):
    settings = get_integration_settings(user["id"], "rapidapi_linkedin", workspace_id=payload.workspace_id)
    config = settings.get("config", {})
    api_key = settings.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="RapidAPI LinkedIn integration is not configured")
    try:
        items = search_linkedin_jobs(api_key, payload.title_filter, payload.location_filter, payload.offset, config.get("host", ""), config.get("endpoint", ""))
        opportunities = [annotate_opportunity(item) for item in rapidapi_items_to_opportunities(items)]
        return {"status": "success", "opportunities": [item for item in opportunities if is_job_like(item)], "raw_count": len(items)}
    except Exception as e:
        logger.error(f"Error searching RapidAPI LinkedIn jobs: {e}")
        raise HTTPException(status_code=502, detail=f"LinkedIn API search failed: {e}")


@router.post("/discovery/apify")
async def discovery_apify(payload: DiscoveryApifyIn, user: dict = Depends(current_user)):
    settings = get_integration_settings(user["id"], "apify", workspace_id=payload.workspace_id)
    config = settings.get("config", {})
    api_key = settings.get("api_key", "")
    actor_id = config.get("actor_id", "")
    if not api_key or not actor_id:
        raise HTTPException(status_code=400, detail="Apify integration is not configured")
    try:
        run_input = build_run_input(payload.url, config.get("input_template", ""))
        items = run_actor_for_items(api_key, actor_id, run_input)
        opportunities = [annotate_opportunity(item) for item in apify_items_to_opportunities(items, source=f"Apify:{actor_id}")]
        return {"status": "success", "opportunities": [item for item in opportunities if is_job_like(item)], "raw_count": len(items)}
    except Exception as e:
        logger.error(f"Error running Apify discovery: {e}")
        raise HTTPException(status_code=502, detail=f"Apify scraper failed: {e}")


@router.post("/discovery/import-url")
async def discovery_import_url(payload: DiscoveryImportUrlIn, user: dict = Depends(current_user)):
    if not is_job_listing_url(payload.url):
        raise HTTPException(status_code=400, detail=_url_error_detail("unsupported_source", "Invalid or unsupported listing URL. Use a supported job listing URL or paste the job details manually."))
    try:
        scraper = get_scraper_for_url(payload.url, payload.source)
        scrape_url = indeed_url_with_work_location_intent(payload.url, payload.work_location_filter)
        scrape_result = scraper.scrape(scrape_url, page_limit=payload.page_limit)
        opportunities, skipped_location = _filter_by_work_location(scrape_result.opportunities, payload.work_location_filter)
        if not opportunities:
            raise HTTPException(status_code=404, detail=_url_error_detail("no_content", "No usable job content was found at the provided URL.", scraper.source_name.lower()))
        import_result = import_opportunities(opportunities, user["id"], workspace_id=payload.workspace_id)
        return {
            "status": "success" if not import_result.errors else "partial_success",
            "source": scraper.source_name, "page_urls": scrape_result.page_urls,
            "work_location_filter": payload.work_location_filter,
            "jobs_found": import_result.found, "jobs_imported": import_result.imported,
            "jobs_skipped_duplicates": import_result.skipped_duplicates,
            "jobs_skipped_location_filter": skipped_location,
            "found": import_result.found, "imported": import_result.imported,
            "skipped_duplicates": import_result.skipped_duplicates,
            "errors": import_result.errors, "warnings": [*scrape_result.warnings, *import_result.warnings],
            "ids": import_result.ids,
        }
    except HTTPException:
        raise
    except UnsupportedSourceUrl as exc:
        raise HTTPException(status_code=400, detail=_url_error_detail("unsupported_source", str(exc)))
    except ScraperError as exc:
        raise _scraper_error_response(exc, payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_url_error_detail("invalid_url", str(exc) or "Invalid URL. Please check the link and try again."))


@router.post("/discovery/import")
async def discovery_import(payload: DiscoveryImportIn, user: dict = Depends(current_user)):
    result = import_opportunities(payload.opportunities, user["id"], workspace_id=payload.workspace_id)
    if result.errors and not result.imported:
        logger.error(f"Error importing discovered opportunities: {result.errors}")
        raise HTTPException(status_code=500, detail="Failed to import discovered opportunities")
    return {
        "status": "success" if not result.errors else "partial_success",
        "ids": result.ids, "count": result.imported,
        "found": result.found, "imported": result.imported,
        "skipped_duplicates": result.skipped_duplicates,
        "errors": result.errors, "warnings": result.warnings,
    }


@router.post("/discovery/manual-entry")
async def discovery_manual_entry(payload: ManualEntryIn, user: dict = Depends(current_user)):
    opportunity = {
        "title": payload.title.strip(),
        "company": payload.company.strip() if payload.company else "",
        "description": payload.description.strip(),
        "raw_text": payload.description.strip(),
        "url": payload.url.strip() if payload.url else "",
        "location": payload.location.strip() if payload.location else "",
        "remote_type": payload.remote_type.strip() if payload.remote_type else "",
        "salary_min": payload.salary_min, "salary_max": payload.salary_max,
        "deadline": payload.deadline.strip() if payload.deadline else "",
        "source": payload.source.strip() if payload.source else "Manual",
        "opportunity_type": payload.opportunity_type,
    }
    result = import_opportunities([opportunity], user["id"], workspace_id=payload.workspace_id)
    if result.errors and not result.imported:
        raise HTTPException(status_code=500, detail=result.errors[0])
    return {
        "status": "success" if not result.errors else "partial_success",
        "id": result.ids[0] if result.ids else None, "ids": result.ids,
        "imported": result.imported, "skipped_duplicates": result.skipped_duplicates,
        "warnings": result.warnings, "errors": result.errors,
    }
