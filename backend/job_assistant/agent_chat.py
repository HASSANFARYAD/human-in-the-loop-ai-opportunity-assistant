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


def _profile_context(profile: Dict[str, Any]) -> str:
    """Compact, human-readable snapshot of the user's profile for grounding."""
    if not profile:
        return "No profile on file yet."
    lines: List[str] = []
    for label, key in (("Name", "name"), ("Target roles", "target_roles"),
                       ("Skills", "skills"), ("Industries", "industries"),
                       ("Location", "location"), ("Summary", "summary")):
        value = str(profile.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value[:400]}")
    cv = str(profile.get("cv_text") or "").strip()
    if cv:
        lines.append(f"Resume excerpt: {cv[:800]}")
    return "\n".join(lines) or "No profile details on file yet."


def _opportunities_context(opportunities: Optional[List[Dict[str, Any]]]) -> str:
    """Compact list of the user's saved opportunities for grounding."""
    if not opportunities:
        return "No saved opportunities yet."
    lines: List[str] = []
    for opp in opportunities[:10]:
        title = str(opp.get("title") or "Untitled").strip()
        company = str(opp.get("company") or "").strip()
        score = opp.get("match_score") or (opp.get("evaluation") or {}).get("match_score")
        bits = [f"#{opp.get('id')}", title]
        if company:
            bits.append(f"@ {company}")
        if score:
            bits.append(f"({score}% match)")
        lines.append(" ".join(str(b) for b in bits))
    return "\n".join(lines)


def chat_reply(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    profile: Optional[Dict[str, Any]] = None,
    opportunities: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[int] = None,
) -> str:
    """Generate a genuine, grounded, multi-turn conversational reply.

    Unlike the intent router, this produces a natural-language answer that is
    aware of the user's profile, saved opportunities, and the running
    conversation — so the chat behaves like a real assistant rather than a
    one-shot classifier.
    """
    transcript = ""
    for turn in (history or [])[-10:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = str(turn.get("content", "")).strip()
        if content:
            transcript += f"{role}: {content[:800]}\n"

    system = (
        "You are a warm, sharp career assistant inside a job-application app. "
        "Hold a natural, multi-turn conversation: answer follow-ups, remember "
        "what was said, ask a clarifying question when it helps. Be concise and "
        "practical, use the user's own data when relevant, and never invent jobs "
        "or facts that aren't in the context. You can also act on the user's "
        "behalf — if they want it, tell them you can search for jobs, tailor "
        "their resume to a saved opportunity, or run interview prep, and that "
        "they just need to ask.\n\n"
        f"User profile:\n{_profile_context(profile or {})}\n\n"
        f"Saved opportunities:\n{_opportunities_context(opportunities)}"
    )
    user = (
        (f"Conversation so far:\n{transcript}\n" if transcript else "")
        + f"User: {message}\n\nReply as the assistant."
    )

    reply = ai_orchestrator.ask(system, user, user_id=user_id, task_type="agent_chat")
    if reply:
        return reply
    return (
        "I can help you find jobs, tailor your resume to a specific opportunity, "
        "or prep you for interviews — what would you like to start with?"
    )


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
