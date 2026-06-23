"""Conversational agent layer.

A single chat entry point classifies the user's intent and routes to the
existing capabilities (job search, resume tailoring, interview prep). This
module owns the parts with no dependency on the API layer:

* ``classify_intent`` — LLM intent classification (via ai_orchestrator).
* ``run_job_search`` — the Job Search Agent, built on the real public
  discovery connectors and the existing scorer (never fabricated listings).

Resume tailoring and interview prep are executed in ``api.py`` because they
reuse helpers defined there; this module stays import-cycle free.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from job_assistant.ai_orchestrator import ai_orchestrator
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.scoring import score_job

logger = logging.getLogger(__name__)

VALID_INTENTS = {"job_search", "tailor_resume", "interview_prep", "chat"}

_INTENT_SCHEMA_HINT = {
    "intents": ["job_search"],
    "search_query": "",
    "job_reference": "",
    "reply": "",
}


def classify_intent(message: str, history: Optional[List[Dict[str, str]]] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Classify a user message into one or more agent intents.

    Returns ``{"intents": [...], "search_query": str, "job_reference": str,
    "reply": str}``. Compound requests yield multiple intents in run order.
    """
    history_text = ""
    for turn in (history or [])[-6:]:
        role = turn.get("role", "user")
        content = str(turn.get("content", ""))[:500]
        history_text += f"{role}: {content}\n"

    system = (
        "You route a career-assistant user message to one or more agents. "
        "Return ONLY JSON with keys: intents (array, ordered, from "
        "[job_search, tailor_resume, interview_prep, chat]), search_query "
        "(string for job_search), job_reference (company/title the user named "
        "for tailoring/prep, else empty), reply (a short natural-language "
        "reply ONLY when intents is exactly [chat], else empty). "
        "Pick chat for greetings or questions that need no agent."
    )
    user = f"Conversation so far:\n{history_text}\nUser message: {message}\n\nClassify it."

    data = ai_orchestrator.ask_json(system, user, dict(_INTENT_SCHEMA_HINT), user_id=user_id, task_type="agent_routing")

    intents = [i for i in (data.get("intents") or []) if i in VALID_INTENTS]
    if not intents:
        intents = ["chat"]
    return {
        "intents": intents,
        "search_query": str(data.get("search_query") or "").strip(),
        "job_reference": str(data.get("job_reference") or "").strip(),
        "reply": str(data.get("reply") or "").strip(),
    }


def _profile_search_query(profile: Dict[str, Any]) -> str:
    return " ".join(
        str(profile.get(key, "")) for key in ("target_roles", "skills", "industries") if profile.get(key)
    ).strip()


def run_job_search(
    profile: Dict[str, Any],
    query: str = "",
    *,
    user_id: Optional[int] = None,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """Job Search Agent: discover real listings and score them against the profile.

    Returns scored opportunity previews (not persisted) sorted by match score.
    Uses the app's existing public discovery connectors — no scraping or
    fabricated listings.
    """
    effective_query = query.strip() or _profile_search_query(profile)
    if not effective_query:
        return []

    opportunities = discover_public_opportunities(query=effective_query, limit_per_source=10)
    results: List[Dict[str, Any]] = []
    for opp in opportunities[: max(1, limit) * 2]:
        evaluation: Dict[str, Any] = {}
        if profile:
            try:
                evaluation = score_job(profile, opp, user_id=user_id)
            except Exception as exc:  # scoring must not sink the whole search
                logger.warning("Scoring failed during job search: %s", exc)
        results.append(
            {
                "title": opp.get("title", ""),
                "company": opp.get("company", ""),
                "location": opp.get("location", ""),
                "url": opp.get("url", ""),
                "source": opp.get("source", ""),
                "opportunity_type": opp.get("opportunity_type", "job"),
                "match_score": int(evaluation.get("match_score", 0) or 0),
                "priority": evaluation.get("priority", ""),
                "good_fit": evaluation.get("good_fit", ""),
            }
        )

    results.sort(key=lambda r: r["match_score"], reverse=True)
    return results[: max(1, limit)]
