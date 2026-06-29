from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from job_assistant.db.company_research import (
    cache_company_profile,
    get_cached_company_profile,
)
from job_assistant.services.ai_providers import ask_json as ask_json_direct

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_BRIEF: Dict[str, Any] = {
    "description": "",
    "industry": "",
    "headquarters": "",
    "size": "",
    "recent_news": [],
    "products_and_services": [],
    "culture_and_values": "",
    "known_interview_process": "",
    "source": "fallback",
}


def _research_via_ai(company_name: str) -> Dict[str, Any]:
    """Use the default AI provider to generate a company brief based on
    publicly known information in its training data."""
    system = (
        "You are a company research analyst. Return JSON only with these keys: "
        "description (2-3 sentences), industry, headquarters, size (employee count range), "
        "recent_news (list of 2-3 notable recent developments as strings), "
        "products_and_services (list of main products/services as strings), "
        "culture_and_values (1-2 sentences), "
        "known_interview_process (1-2 sentences if known, else empty string). "
        "Do not fabricate details. Leave fields empty or null if unknown."
    )
    prompt = f"Research company: {company_name}. Provide the most relevant and up-to-date information available."
    try:
        result = ask_json_direct(system, prompt, DEFAULT_FALLBACK_BRIEF)
        if isinstance(result, dict) and not result.get("_ai_error"):
            result.setdefault("source", "ai_research")
            return result
    except Exception as exc:
        logger.warning("AI company research failed for %s: %s", company_name, exc)
    return dict(DEFAULT_FALLBACK_BRIEF)


def get_company_brief(
    company_name: str,
    *,
    user_id: Optional[int] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Return a company research brief, using cached data if available.

    Parameters
    ----------
    company_name : str
        The company name to research.
    user_id : int, optional
        The user making the request (for audit/cache attribution).
    force_refresh : bool
        If True, bypass the cache and re-research.

    Returns
    -------
    dict with keys: description, industry, headquarters, size, recent_news,
    products_and_services, culture_and_values, known_interview_process, source.
    """
    if not company_name or not company_name.strip():
        return dict(DEFAULT_FALLBACK_BRIEF)

    if not force_refresh:
        cached = get_cached_company_profile(company_name.strip())
        if cached is not None:
            profile = cached.get("profile") or {}
            logger.info("Returning cached company brief for %s", company_name.strip())
            return profile

    brief = _research_via_ai(company_name.strip())

    try:
        cache_company_profile(company_name.strip(), brief, source=brief.get("source", "ai_research"), user_id=user_id)
    except Exception as exc:
        logger.warning("Failed to cache company profile for %s: %s", company_name, exc)

    return brief


def build_company_context(
    company_name: str,
    *,
    user_id: Optional[int] = None,
    force_refresh: bool = False,
) -> str:
    """Return a human-readable company context string for use in prompts."""
    brief = get_company_brief(company_name, user_id=user_id, force_refresh=force_refresh)
    source = brief.get("source", "unknown")
    parts: list[str] = []
    if brief.get("description"):
        parts.append(f"About: {brief['description']}")
    if brief.get("industry"):
        parts.append(f"Industry: {brief['industry']}")
    if brief.get("headquarters"):
        parts.append(f"HQ: {brief['headquarters']}")
    if brief.get("size"):
        parts.append(f"Size: {brief['size']}")
    if brief.get("culture_and_values"):
        parts.append(f"Culture: {brief['culture_and_values']}")
    if brief.get("known_interview_process"):
        parts.append(f"Interview process: {brief['known_interview_process']}")
    if brief.get("recent_news"):
        news = "; ".join(str(item) for item in brief["recent_news"] if item)
        if news:
            parts.append(f"Recent news: {news}")
    if brief.get("products_and_services"):
        prods = ", ".join(str(item) for item in brief["products_and_services"] if item)
        if prods:
            parts.append(f"Products/Services: {prods}")
    if not parts:
        return ""
    context = "\n".join(parts)
    return f"Company context ({source}):\n{context}"
