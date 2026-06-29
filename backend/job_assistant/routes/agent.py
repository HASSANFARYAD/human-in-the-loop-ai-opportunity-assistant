from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from job_assistant.agent_chat import (
    chat_reply,
    chat_reply_stream,
    classify_intent,
    extract_memories_from_conversation,
    generate_suggestions,
    run_job_search,
)
from job_assistant.auth import current_user
from job_assistant.db import (
    add_conversation_message,
    create_conversation,
    create_memory,
    delete_conversation,
    delete_memory,
    get_agent_persona,
    get_conversation,
    get_conversation_messages,
    get_evaluation,
    get_job,
    get_profile,
    list_conversations,
    list_jobs,
    list_memories,
    record_agent_feedback,
    save_interview_prep,
    save_resume_review,
    set_conversation_state,
    update_agent_persona,
    update_conversation,
    update_memory,
)
from job_assistant.services.scoring import score_job

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentChatIn(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    conversation_id: Optional[int] = None
    workspace_id: Optional[int] = None


class ConversationCreateIn(BaseModel):
    title: str = ""
    workspace_id: Optional[int] = None


class ConversationUpdateIn(BaseModel):
    title: str


class AgentFeedbackIn(BaseModel):
    message_id: int
    rating: str
    workspace_id: Optional[int] = None


class PersonaIn(BaseModel):
    tone: str = "friendly"
    detail_level: str = "balanced"
    focus_area: str = "general"


class MemoryIn(BaseModel):
    key: str
    value: str
    source: str = "manual"


class MemoryUpdateIn(BaseModel):
    key: str
    value: str


class MemoryOut(BaseModel):
    id: int
    key: str
    value: str
    source: str
    created_at: str
    updated_at: str


class AIAskIn(BaseModel):
    workspace_id: Optional[int] = None
    system: str = "You are a helpful assistant. Return JSON only."
    prompt: str
    fallback: dict[str, Any] = Field(default_factory=dict)
    task_type: str = "general"
    prompt_version: str = ""


def _resolve_job_for_reference(user_id: int, reference: str, workspace_id: Optional[int] = None) -> Optional[dict[str, Any]]:
    jobs = list_jobs(user_id, workspace_id=workspace_id)
    if not jobs:
        return None
    ref = (reference or "").strip().lower()
    if ref:
        for job in jobs:
            haystack = f"{job.get('title', '')} {job.get('company', '')}".lower()
            if ref in haystack:
                return job
    return jobs[0]


def _run_agent_intent(intent: str, routing: dict[str, Any], profile: dict[str, Any], user_id: int, workspace_id: Optional[int], *, message: str = "", history: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
    if intent == "job_search":
        listings = run_job_search(profile, routing["search_query"], user_id=user_id, history=history)
        return {"agent": "job_search", "type": "listings", "data": listings,
                "message": f"Found {len(listings)} matching opportunity/opportunities." if listings
                else "No matching listings found right now. Try refining your roles or skills."}

    if intent in ("tailor_resume", "interview_prep"):
        job = _resolve_job_for_reference(user_id, routing["job_reference"], workspace_id)
        if not job:
            return {"agent": intent, "type": "error",
                    "message": "I couldn't find a saved opportunity to work from. Import or open a job first."}

        if intent == "tailor_resume":
            if not _profile_has_resume_context(profile):
                return {"agent": intent, "type": "error",
                        "message": "Add your resume or profile details before I can tailor a resume."}
            tailored = _llm_tailored_resume(profile, job, user_id)
            saved = save_resume_review(user_id, tailored, int(job["id"]))
            return {"agent": intent, "type": "tailored_resume", "job": {"id": job["id"], "title": job.get("title"), "company": job.get("company")}, "data": saved}

        evaluation = get_evaluation(int(job["id"]), user_id) or {}
        if not evaluation:
            try:
                evaluation = score_job(profile, job, user_id=user_id)
            except Exception:
                evaluation = {}
        prep = _llm_interview_prep(profile, job, evaluation, user_id)
        saved = save_interview_prep(user_id, int(job["id"]), prep)
        return {"agent": intent, "type": "interview_prep", "job": {"id": job["id"], "title": job.get("title"), "company": job.get("company")}, "data": saved}

    opportunities = list_jobs(user_id, workspace_id=workspace_id)
    reply = chat_reply(message, history=history, profile=profile, opportunities=opportunities, user_id=user_id)
    return {"agent": "chat", "type": "message", "message": reply}


def _profile_has_resume_context(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    return any(str(profile.get(key) or "").strip() for key in ["cv_text", "skills", "target_roles", "preferred_role"])


def _require_ai_configuration(user_id: int, task_type: str) -> None:
    from job_assistant.ai_orchestrator import ai_orchestrator
    route = ai_orchestrator.resolve_route(user_id, task_type=task_type)
    if not (route.settings.get("api_key") or "").strip():
        raise HTTPException(
            status_code=400,
            detail="LLM provider configuration is missing in database settings. Configure an active AI provider before generating this output.",
        )


def _llm_tailored_resume(profile: dict[str, Any], job: dict[str, Any], user_id: int) -> dict[str, Any]:
    from job_assistant.services.job_context import build_job_context
    from job_assistant.ai_orchestrator import ai_orchestrator
    fallback = _generate_tailored_resume(profile, job)
    route = ai_orchestrator.resolve_route(user_id, task_type="resume_tailoring")
    job_context = build_job_context(profile, job)
    system = (
        "You are an expert resume writer. Return JSON only. Create a truthful tailored resume draft grounded only in "
        "the supplied resume/profile and job description. Do not invent employers, degrees, certifications, metrics, or credentials."
    )
    context = {
        "resume_text": (profile.get("cv_text") or "")[:4000],
        "profile": {k: v for k, v in (profile or {}).items() if k != "cv_text"},
        "job": {
            "title": job.get("title"), "company": job.get("company"),
            "description": (job.get("description") or job.get("raw_text") or "")[:4000],
            "location": job.get("location"), "remote_type": job.get("remote_type"),
            "keywords": job_context["keywords"][:20], "focus_areas": job_context["focus_areas"][:10],
            "highlights": job_context["highlights"][:5],
        },
        "required_output_keys": [
            "tailored_summary", "tailored_experience_bullets", "skills_to_emphasize",
            "keywords_to_include", "optional_cover_note", "application_guidance", "resume_draft",
        ],
    }
    context_json = json.dumps(context, default=str)
    if len(context_json) > 15000:
        context_json = context_json[:15000]
    tailored = ai_orchestrator.ask_json(
        system, context_json, fallback,
        user_id=user_id, task_type="resume_tailoring", workspace_id=job.get("workspace_id"),
    )
    for key, value in fallback.items():
        tailored.setdefault(key, value)
    tailored["resume_draft"] = _resume_draft_to_text(tailored.get("resume_draft"))
    tailored["type"] = "tailored_resume"
    tailored["target_role"] = tailored.get("target_role") or job.get("title") or "target role"
    tailored["company"] = tailored.get("company") or job.get("company") or ""
    tailored["using_fallback"] = route.source == "fallback" or bool(tailored.get("_ai_error"))
    tailored["generation_source"] = "local_fallback" if tailored["using_fallback"] else "llm"
    if tailored.get("_ai_error"):
        tailored["ai_error"] = "AI generation failed; local fallback was used."
        tailored.pop("_ai_error", None)
    return tailored


def _llm_interview_prep(profile: dict[str, Any], job: dict[str, Any], evaluation: dict[str, Any], user_id: int) -> dict[str, Any]:
    from job_assistant.services.job_context import build_job_context
    from job_assistant.ai_orchestrator import ai_orchestrator
    from job_assistant.db import list_resume_reviews
    _require_ai_configuration(user_id, "interview_prep")
    fallback = _generate_interview_prep(profile, job, evaluation)
    latest_reviews = list_resume_reviews(user_id, job_id=int(job["id"]), limit=1)
    job_context = build_job_context(profile, job)
    system = (
        "You are an expert interview coach. Return JSON only with keys: behavioral_questions, technical_questions, "
        "role_specific_questions, company_job_specific_questions, suggested_answer_outlines, star_format_guidance, "
        "weakness_improvement_prompts, candidate_questions, final_preparation_checklist."
    )
    context = {
        "user_profile": {k: v for k, v in (profile or {}).items() if k != "cv_text"},
        "resume_text": (profile.get("cv_text") or "")[:4000],
        "selected_opportunity": {k: v for k, v in (job or {}).items() if k not in ("raw_text", "description")},
        "company_name": job.get("company"),
        "role_title": job.get("title"),
        "job_description": (job.get("description") or "")[:4000],
        "required_skills": ((job.get("raw_text") or job.get("description") or "")[:3000]),
        "job_keywords": job_context["keywords"][:20],
        "job_focus_areas": job_context["focus_areas"][:10],
        "job_highlights": job_context["highlights"][:5],
        "ai_score": evaluation,
        "resume_review_findings": latest_reviews[0] if latest_reviews else {},
    }
    context_json = json.dumps(context, default=str)
    if len(context_json) > 15000:
        context_json = context_json[:15000]
    prep = ai_orchestrator.ask_json(
        system, context_json, fallback,
        user_id=user_id, task_type="interview_prep", workspace_id=job.get("workspace_id"),
    )
    if prep.get("_ai_error"):
        raise HTTPException(status_code=502, detail=f"LLM interview preparation failed: {prep.get('_ai_error')}")
    prep.setdefault("generation_source", "llm")
    return prep


def _generate_tailored_resume(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    from job_assistant.services.job_context import build_job_context, choose_primary_focus_area
    context = build_job_context(profile, job)
    role = context["title"]
    company = context["company"]
    skills = context["skills"]
    keywords = context["keywords"]
    focus_areas = context["focus_areas"]
    highlights = context["highlights"]
    emphasized_skills = [skill for skill in skills if skill.lower() in " ".join(keywords).lower()] or skills[:8] or keywords[:8]
    primary_focus = choose_primary_focus_area(focus_areas)
    secondary_focus = next((area for area in focus_areas if area != primary_focus), primary_focus)
    highlight = highlights[0] if highlights else ""
    summary = (
        f"{profile.get('years_experience') or 'Experienced'} professional targeting {role} at {company}, "
        f"with hands-on experience in {', '.join(emphasized_skills[:5]) or 'the role requirements'} and a clear fit for {primary_focus.lower()}."
    )
    bullets = [
        f"Delivered work aligned with {primary_focus.lower()} using {', '.join(emphasized_skills[:4]) or 'relevant tools and practices'}.",
        f"Translated {secondary_focus.lower()} requirements into maintainable, measurable solutions that can be referenced in the {role} resume.",
        f"Collaborated across stakeholders to ship reliable improvements; job-specific cue: {highlight[:120] or 'highlight the most relevant project outcome from your history'}.",
    ]
    draft = "\n".join([
        "Professional Summary", summary, "",
        "Selected Experience Bullets",
        *[f"- {bullet}" for bullet in bullets], "",
        "Skills", ", ".join(emphasized_skills[:12] or keywords[:12]),
    ])
    return {
        "type": "tailored_resume", "target_role": role, "company": company,
        "tailored_summary": summary, "tailored_experience_bullets": bullets,
        "skills_to_emphasize": emphasized_skills[:12], "keywords_to_include": keywords,
        "job_focus_areas": focus_areas, "job_highlights": highlights,
        "optional_cover_note": f"I am interested in the {role} role at {company} because the posting emphasizes {primary_focus.lower()} and {secondary_focus.lower()}, which maps directly to my background.",
        "application_guidance": [
            "Keep claims grounded in your real resume and project history.",
            "Add metrics to the bullets before submitting.",
            "Mirror the most relevant job keywords where they truthfully match your experience.",
        ],
        "resume_draft": draft, "generation_source": "local_fallback",
    }


def _generate_interview_prep(profile: dict[str, Any], job: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    from job_assistant.services.job_context import build_job_context, choose_primary_focus_area
    context = build_job_context(profile, job)
    role = context["title"]
    company = context["company"]
    focus_areas = context["focus_areas"]
    highlights = context["highlights"]
    skills = context["skills"]
    primary_focus = choose_primary_focus_area(focus_areas)
    other_focuses = [area for area in focus_areas if area != primary_focus]
    secondary_focus = other_focuses[0] if other_focuses else primary_focus
    third_focus = other_focuses[1] if len(other_focuses) > 1 else primary_focus
    skill_line = ", ".join(skills[:4] or context["keywords"][:4] or ["your stack"])
    highlight_line = highlights[0] if highlights else f"the requirements for {role}"
    return {
        "summary": f"Interview preparation for {role} at {company}.",
        "behavioral_questions": [
            f"Tell me about a time you delivered {primary_focus.lower()} under a tight timeline.",
            f"Describe a situation where you had to balance {secondary_focus.lower()} with quality or stakeholder expectations.",
            f"Give an example of improving a process or system similar to the work described in this posting.",
        ],
        "technical_questions": [
            f"Walk through how your skills in {skill_line} apply to {primary_focus.lower()} for this role.",
            f"How would you approach a production issue that touches {secondary_focus.lower()} and needs careful validation?",
            f"What tradeoffs would you consider when designing a solution for {third_focus.lower()} in a fast-moving environment?",
        ],
        "role_specific_questions": [
            f"What attracts you to the {role} responsibilities at {company}?",
            f"Which requirement in the job description best matches your recent experience with {primary_focus.lower()}?",
        ],
        "company_job_specific_questions": [
            f"The posting highlights: {highlight_line[:140]}. How would you show direct experience with that?",
            f"What part of the {role} role at {company} feels most aligned with your background?",
        ],
        "suggested_answer_outlines": [
            f"Use STAR, then close by tying the answer back to {primary_focus.lower()} and the impact you delivered.",
            f"Reference a concrete project that shows {secondary_focus.lower()} and keep the answer under two minutes.",
        ],
        "star_format_guidance": [
            "Situation: give only the minimum context needed.",
            "Task: state the goal or constraint clearly.",
            "Action: focus on what you personally did.",
            "Result: include a measurable or observable outcome.",
        ],
        "weakness_improvement_prompts": [
            f"Prepare one example that proves you can handle {primary_focus.lower()} without inventing details.",
            f"Prepare one example that proves you can communicate tradeoffs around {secondary_focus.lower()}.",
        ],
        "candidate_questions": [
            f"What does success look like for {role} in the first 30, 60, and 90 days?",
            f"Where does {company} need the most help relative to {highlight_line[:90]}?",
        ],
        "final_preparation_checklist": [
            f"Have one example ready for {primary_focus.lower()}",
            f"Have one example ready for {secondary_focus.lower()}",
            "Prepare one metric-driven story and one learning story.",
            "Review the company, the job description, and your resume side by side before the interview.",
        ],
        "talking_points": [
            evaluation.get("good_fit") or f"Highlight direct overlap between your experience and the {role} responsibilities.",
            f"Prepare one metric-driven achievement and one story tied to {primary_focus.lower()}.",
        ],
        "questions_to_ask": [
            "What would success look like in the first 90 days?",
            f"Which team priorities are driving this opening at {company}?",
        ],
        "generation_source": "local_fallback",
    }


def _resume_draft_to_text(draft: Any) -> str:
    if draft is None:
        return ""
    if isinstance(draft, str):
        return draft
    if isinstance(draft, (list, tuple)):
        return "\n".join(_resume_draft_to_text(item) for item in draft if item is not None)
    if isinstance(draft, dict):
        lines: list[str] = []
        for key, value in draft.items():
            label = str(key).replace("_", " ").title()
            text = _resume_draft_to_text(value)
            if not text.strip():
                continue
            if "\n" in text:
                lines.append(f"{label}:\n{text}")
            else:
                lines.append(f"{label}: {text}")
        return "\n\n".join(lines)
    return str(draft)


@router.post("/agent/chat")
async def agent_chat(payload: AgentChatIn, user: dict = Depends(current_user)):
    user_id = user["id"]
    routing = classify_intent(payload.message, history=payload.history, user_id=user_id)
    profile = get_profile(user_id) or {}
    sections = [_run_agent_intent(intent, routing, profile, user_id, payload.workspace_id, message=payload.message, history=payload.history) for intent in routing["intents"]]
    return {"intents": routing["intents"], "sections": sections}


@router.post("/agent/chat/stream")
async def agent_chat_stream(payload: AgentChatIn, user: dict = Depends(current_user)):
    user_id = user["id"]
    workspace_id = payload.workspace_id
    history = payload.history
    message = payload.message
    conversation_id = payload.conversation_id

    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    def event_stream():
        nonlocal conversation_id
        try:
            if not conversation_id:
                title = (message[:80] + "...") if len(message) > 80 else message
                conversation_id = create_conversation(user_id, title, workspace_id=workspace_id)
                yield _sse("conversation", {"conversation_id": conversation_id})

            add_conversation_message(conversation_id, "user", message)

            routing = classify_intent(message, history=history, user_id=user_id)
            profile = get_profile(user_id) or {}
            yield _sse("intents", {"intents": routing["intents"]})

            intent_to_state = {"job_search": "searching", "tailor_resume": "tailoring", "interview_prep": "interviewing", "chat": "chatting"}
            first_state = intent_to_state.get(routing["intents"][0], "idle") if routing["intents"] else "idle"
            set_conversation_state(conversation_id, user_id, first_state)

            assistant_sections: list[dict[str, Any]] = []
            for intent in routing["intents"]:
                try:
                    if intent == "chat":
                        opportunities = list_jobs(user_id, workspace_id=workspace_id)
                        yield _sse("section", {"agent": "chat", "type": "message", "message": ""})
                        full_reply = ""
                        stream_iter = chat_reply_stream(
                            message, history=history, profile=profile,
                            opportunities=opportunities, user_id=user_id,
                        )
                        for token in stream_iter:
                            full_reply += token
                            yield _sse("delta", {"text": token})
                        assistant_sections.append({"agent": "chat", "type": "message", "message": full_reply})

                        try:
                            suggestions = generate_suggestions(message, full_reply, history=history, user_id=user_id)
                            if suggestions:
                                yield _sse("suggestions", {"suggestions": suggestions})
                        except Exception:
                            pass
                        continue

                    section = _run_agent_intent(intent, routing, profile, user_id, workspace_id, message=message, history=history)
                    assistant_sections.append(section)
                except HTTPException as exc:
                    section = {"agent": intent, "type": "error", "message": str(exc.detail)}
                    assistant_sections.append(section)
                    yield _sse("section", section)
                    continue
                except Exception:
                    section = {"agent": intent, "type": "error", "message": "Something went wrong while running this step."}
                    assistant_sections.append(section)
                    yield _sse("section", section)
                    continue
                yield _sse("section", section)

            content = next((s.get("message", "") for s in assistant_sections if s.get("type") == "message"), "")
            msg_id = add_conversation_message(conversation_id, "assistant", content, sections=assistant_sections)
            yield _sse("done", {"conversation_id": conversation_id, "message_id": msg_id})

            try:
                extract_memories_from_conversation(message, content, history=history, user_id=user_id)
            except Exception:
                pass
        except Exception:
            yield _sse("error", {"message": "The assistant could not complete your request."})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/agent/conversations")
async def create_conversation_endpoint(payload: ConversationCreateIn, user: dict = Depends(current_user)):
    title = payload.title.strip() or "New conversation"
    cid = create_conversation(user["id"], title, workspace_id=payload.workspace_id)
    return {"conversation_id": cid, "title": title}


@router.get("/agent/conversations")
async def list_conversations_endpoint(limit: int = 50, user: dict = Depends(current_user)):
    return list_conversations(user["id"], limit=limit)


@router.get("/agent/conversations/{conversation_id}")
async def get_conversation_endpoint(conversation_id: int, user: dict = Depends(current_user)):
    conv = get_conversation(conversation_id, user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(conversation_id)
    return {**conv, "messages": messages}


@router.patch("/agent/conversations/{conversation_id}")
async def update_conversation_endpoint(conversation_id: int, payload: ConversationUpdateIn, user: dict = Depends(current_user)):
    ok = update_conversation(conversation_id, user["id"], payload.dict())
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.delete("/agent/conversations/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: int, user: dict = Depends(current_user)):
    ok = delete_conversation(conversation_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok"}


@router.post("/agent/conversations/{conversation_id}/feedback")
async def post_agent_feedback(conversation_id: int, payload: AgentFeedbackIn, user: dict = Depends(current_user)):
    try:
        record_agent_feedback(user["id"], conversation_id, payload.message_id, payload.rating, workspace_id=payload.workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success"}


@router.get("/agent/persona")
async def get_persona(user: dict = Depends(current_user)):
    return {"persona": get_agent_persona(user["id"])}


@router.put("/agent/persona")
async def put_persona(payload: PersonaIn, user: dict = Depends(current_user)):
    update_agent_persona(user["id"], payload.dict())
    return {"status": "success"}


@router.get("/agent/memories")
async def list_agent_memories(user: dict = Depends(current_user)):
    memories = list_memories(user["id"])
    return [
        {
            "id": m["memory_id"],
            "key": m["key"],
            "value": m["value"],
            "source": m.get("source", "manual"),
            "created_at": m.get("created_at", ""),
            "updated_at": m.get("updated_at", ""),
        }
        for m in memories
    ]


@router.post("/agent/memories")
async def create_agent_memory(payload: MemoryIn, user: dict = Depends(current_user)):
    try:
        mid = create_memory(user["id"], payload.key, payload.value, source=payload.source)
        return {"id": mid, "status": "success"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/agent/memories/{memory_id}")
async def update_agent_memory(memory_id: int, payload: MemoryUpdateIn, user: dict = Depends(current_user)):
    try:
        ok = update_memory(memory_id, user["id"], payload.key, payload.value)
        if not ok:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"status": "success"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/agent/memories/{memory_id}")
async def delete_agent_memory(memory_id: int, user: dict = Depends(current_user)):
    ok = delete_memory(memory_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "ok"}
