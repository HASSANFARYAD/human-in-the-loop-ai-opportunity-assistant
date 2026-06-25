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
from job_assistant.db import get_active_prompt, get_agent_persona, get_memories_context, create_memory, list_memories
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.scoring import score_job

logger = logging.getLogger(__name__)

VALID_INTENTS = {"job_search", "tailor_resume", "interview_prep", "chat"}

_INTENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "route_intent",
            "description": "Route a career-assistant user message to one or more capabilities. "
                           "Pick chat for greetings, casual conversation, or questions that need "
                           "no agent action. For compound requests, order intents appropriately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intents": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(VALID_INTENTS)},
                        "description": "Ordered list of intents to execute",
                    },
                    "search_query": {
                        "type": "string",
                        "description": "Job search query when intents includes job_search",
                    },
                    "job_reference": {
                        "type": "string",
                        "description": "Company name or job title the user referenced for tailoring or interview prep",
                    },
                },
                "required": ["intents"],
            },
        },
    },
]
_INTENT_TOOLS_FALLBACK = {"intents": ["chat"], "search_query": "", "job_reference": ""}


def classify_intent(message: str, history: Optional[List[Dict[str, str]]] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Classify a user message into one or more agent intents using tool calling.

    Returns ``{"intents": [...], "search_query": str, "job_reference": str}``.
    Compound requests yield multiple intents in run order.
    """
    history_text = ""
    for turn in (history or [])[-6:]:
        role = turn.get("role", "user")
        content = str(turn.get("content", ""))[:500]
        history_text += f"{role}: {content}\n"

    system = (
        "You route a career-assistant user message to one or more agents. "
        "Use the route_intent tool to decide which capabilities to invoke."
    )
    user = f"Conversation so far:\n{history_text}\nUser message: {message}\n\nClassify it."

    data = ai_orchestrator.ask_tool_json(system, user, _INTENT_TOOLS, dict(_INTENT_TOOLS_FALLBACK), user_id=user_id, task_type="agent_routing")

    intents = [i for i in (data.get("intents") or []) if i in VALID_INTENTS]
    if not intents:
        intents = ["chat"]
    return {
        "intents": intents,
        "search_query": str(data.get("search_query") or "").strip(),
        "job_reference": str(data.get("job_reference") or "").strip(),
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


def _build_chat_system(profile: Optional[Dict[str, Any]], opportunities: Optional[List[Dict[str, Any]]], user_id: Optional[int] = None) -> str:
    """Build the system prompt from DB template (or hardcoded fallback) + user data."""
    template = get_active_prompt("chat_system") if user_id else ""
    if not template:
        template = (
            "You are a warm, sharp career assistant inside a job-application app. "
            "Hold a natural, multi-turn conversation: answer follow-ups, remember "
            "what was said, ask a clarifying question when it helps. Be concise and "
            "practical, use the user's own data when relevant, and never invent jobs "
            "or facts that aren't in the context. You can also act on the user's "
            "behalf — if they want it, tell them you can search for jobs, tailor "
            "their resume to a saved opportunity, or run interview prep, and that "
            "they just need to ask."
        )

    persona = get_agent_persona(user_id) if user_id else {}
    persona_notes = ""
    if persona:
        parts = []
        if persona.get("tone"):
            parts.append(f"Tone: {persona['tone']}")
        if persona.get("detail_level"):
            parts.append(f"Detail level: {persona['detail_level']}")
        if persona.get("focus_area"):
            parts.append(f"Focus area: {persona['focus_area']}")
        if parts:
            persona_notes = "User preferences:\n" + "\n".join(parts) + "\n\n"

    memory_context = get_memories_context(user_id) if user_id else ""
    memory_section = f"\n\n{memory_context}" if memory_context else ""

    return (
        f"{template}\n\n"
        f"{persona_notes}"
        f"User profile:\n{_profile_context(profile or {})}\n\n"
        f"Saved opportunities:\n{_opportunities_context(opportunities)}"
        f"{memory_section}"
    )


def chat_reply_stream(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    profile: Optional[Dict[str, Any]] = None,
    opportunities: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[int] = None,
):
    """Generator that yields tokens from the LLM for a grounded chat response."""
    transcript = ""
    for turn in (history or [])[-10:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = str(turn.get("content", "")).strip()
        if content:
            transcript += f"{role}: {content[:800]}\n"

    system = _build_chat_system(profile, opportunities, user_id)
    user = (
        (f"Conversation so far:\n{transcript}\n" if transcript else "")
        + f"User: {message}\n\nReply as the assistant."
    )

    replied = False
    for token in ai_orchestrator.ask_stream(system, user, user_id=user_id, task_type="agent_chat"):
        replied = True
        yield token

    if not replied:
        yield (
            "I can help you find jobs, tailor your resume to a specific opportunity, "
            "or prep you for interviews — what would you like to start with?"
        )


def generate_suggestions(
    message: str,
    reply: str,
    history: Optional[List[Dict[str, str]]] = None,
    user_id: Optional[int] = None,
) -> list[str]:
    """Generate 2-3 follow-up suggestions based on the last exchange."""
    transcript = ""
    for turn in (history or [])[-4:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = str(turn.get("content", ""))[:300]
        if content:
            transcript += f"{role}: {content}\n"

    system = (
        "Given the conversation so far and the assistant's last reply, suggest "
        "2-3 short, natural follow-up questions or actions the user could take next. "
        "Return ONLY a JSON array of strings, each 3-10 words. "
        "Focus on career-relevant next steps."
    )
    user = (
        f"Conversation so far:\n{transcript}\n"
        f"Assistant's last reply: {reply[:600]}\n\n"
        "Suggestions:"
    )

    fallback: list[str] = [
        "Find me relevant jobs",
        "Tailor my resume",
        "Prep me for an interview",
    ]
    data = ai_orchestrator.ask_json(system, user, {"suggestions": fallback}, user_id=user_id, task_type="agent_suggestions")
    raw = data.get("suggestions") or fallback
    return [str(s).strip() for s in raw if isinstance(s, str)][:3] or fallback[:3]


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


def _extract_search_context(history: Optional[List[Dict[str, str]]]) -> str:
    """Extract relevant search terms from recent conversation history."""
    if not history:
        return ""
    context_terms: list[str] = []
    for turn in history[-6:]:
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        msg = content[:500].lower()
        # Look for role/job/location keywords
        for prefix in ("roles like", "jobs in", "positions as", "title like", "looking for", "find me"):
            if prefix in msg[:60]:
                remainder = msg.split(prefix, 1)[-1].split(".")[0].split("?")[0].strip()
                if remainder:
                    context_terms.append(remainder)
        # Also grab "as a ..." patterns
        for prefix in ("as a", "as an"):
            idx = msg.find(prefix)
            if idx != -1 and idx < 100:
                after = msg[idx + len(prefix):].split(".")[0].split("?")[0].split(",")[0].strip()
                if after and len(after) < 60:
                    context_terms.append(after)
    return " ".join(context_terms[-3:])  # keep last 3


def run_job_search(
    profile: Dict[str, Any],
    query: str = "",
    *,
    user_id: Optional[int] = None,
    limit: int = 12,
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Job Search Agent: discover real listings and score them against the profile.

    Returns scored opportunity previews (not persisted) sorted by match score.
    Uses the app's existing public discovery connectors — no scraping or
    fabricated listings.
    """
    base_query = query.strip() or _profile_search_query(profile)
    context = _extract_search_context(history)
    effective_query = (base_query + " " + context).strip() if context else base_query
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


def extract_memories_from_conversation(
    user_message: str,
    reply: str,
    history: Optional[List[Dict[str, str]]] = None,
    user_id: Optional[int] = None,
) -> None:
    """Extract user-specific facts from the conversation and persist them as memories.

    Fire-and-forget: runs after each assistant reply to learn things like
    the user's role, location, preferences, etc. that should persist across
    conversations.
    """
    if not user_id:
        return
    transcript = ""
    for turn in (history or [])[-4:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = str(turn.get("content", ""))[:300]
        if content:
            transcript += f"{role}: {content}\n"

    system = (
        "Extract key facts about the user from this career-assistant conversation. "
        "Return ONLY a JSON object with a 'facts' key containing an array of objects, "
        'each with "key" (short label, lowercase, 1-3 words) and "value" (the fact itself). '
        "Only extract facts that are likely to be long-term useful (role, skills, location, "
        "preferences, experience, background). Skip ephemeral or trivial statements. "
        "Maximum 3 facts per extraction. Example: "
        '[{"key": "current role", "value": "senior software engineer focused on AI/ML"}, '
        '{"key": "location", "value": "San Francisco"}]'
    )
    user = (
        f"Conversation so far:\n{transcript}\n"
        f"User: {user_message}\n"
        f"Assistant: {reply[:600]}\n\n"
        "Extracted facts:"
    )

    try:
        data = ai_orchestrator.ask_json(system, user, {"facts": []}, user_id=user_id, task_type="agent_memory_extraction")
        facts = data.get("facts") or []
        existing_keys = {m.get("key", "").lower() for m in list_memories(user_id)}
        for fact in facts[:3]:
            key = str(fact.get("key", "")).strip().lower()
            value = str(fact.get("value", "")).strip()
            if key and value and len(key) <= 50 and len(value) <= 500:
                if key in existing_keys:
                    continue
                try:
                    create_memory(user_id, key, value, source="extracted")
                    existing_keys.add(key)
                except Exception:
                    logger.warning("Failed to save extracted memory key=%s", key)
    except Exception:
        logger.debug("Memory extraction skipped (best-effort)", exc_info=True)
