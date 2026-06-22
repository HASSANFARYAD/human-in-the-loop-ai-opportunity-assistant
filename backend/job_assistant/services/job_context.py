from __future__ import annotations

import re
from typing import Any, Dict

_STOPWORDS = {
    "about",
    "and",
    "are",
    "asking",
    "at",
    "based",
    "being",
    "build",
    "building",
    "business",
    "can",
    "client",
    "company",
    "developer",
    "engineering",
    "experience",
    "for",
    "from",
    "help",
    "into",
    "join",
    "job",
    "looking",
    "market",
    "more",
    "need",
    "needed",
    "position",
    "role",
    "skills",
    "team",
    "that",
    "the",
    "their",
    "this",
    "work",
    "working",
    "with",
    "you",
    "your",
}

_FOCUS_BUCKETS: list[tuple[str, tuple[str, ...]]] = [
    ("AI / LLM workflows", ("ai", "llm", "openai", "anthropic", "claude", "gpt", "agent", "agents", "memory", "rag", "validation")),
    ("Python / backend delivery", ("python", "backend", "api", "apis", "fastapi", "django", "data", "pipeline", "pipelines", "sql", "postgres", "postgresql")),
    ("React / frontend delivery", ("react", "frontend", "ui", "typescript", "next.js", "javascript", "web", "component")),
    ("Automation / integrations", ("automation", "workflow", "workflows", "zapier", "make", "n8n", "integration", "integrations", "webhook", "webhooks", "rest")),
    ("Cloud / production readiness", ("azure", "aws", "gcp", "docker", "deployment", "production", "monitoring", "scalable", "latency")),
    ("Client-facing collaboration", ("client-facing", "communication", "agile", "scrum", "documentation", "handover", "stakeholder", "documentation", "english")),
]


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def job_text(job: Dict[str, Any]) -> str:
    description = _normalize_text(job.get("description") or "")
    raw_text = _normalize_text(job.get("raw_text") or "")
    parts = [
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        job.get("remote_type", ""),
        description or raw_text,
    ]
    return "\n".join(_normalize_text(part) for part in parts if _normalize_text(part))


def extract_profile_skills(profile: Dict[str, Any], limit: int = 8) -> list[str]:
    raw = _normalize_text(profile.get("skills") or profile.get("cv_text") or "")
    if not raw:
        return []
    skills: list[str] = []
    seen: set[str] = set()
    for part in re.split(r",|\n|;|/", raw):
        cleaned = _normalize_text(part)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        skills.append(cleaned)
        if len(skills) >= limit:
            break
    return skills


def extract_job_keywords(job: Dict[str, Any], limit: int = 12) -> list[str]:
    text = job_text(job)
    keywords: list[str] = []
    seen: set[str] = set()
    for term in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", text):
        key = term.lower()
        if key in _STOPWORDS or key in seen:
            continue
        seen.add(key)
        keywords.append(term)
        if len(keywords) >= limit:
            break
    return keywords


def extract_job_focus_areas(job: Dict[str, Any], limit: int = 4) -> list[str]:
    text = job_text(job).lower()
    title = str(job.get("title") or "").lower()
    scored: list[tuple[int, int, str]] = []
    for index, (label, tokens) in enumerate(_FOCUS_BUCKETS):
        score = 0
        for token in tokens:
            score += text.count(token)
            if token in title:
                score += 2
        if score:
            scored.append((-score, index, label))
    if not scored:
        keywords = extract_job_keywords(job, limit=limit)
        return [f"Core focus: {keyword}" for keyword in keywords]
    scored.sort()
    return [label for _, _, label in scored[:limit]]


def extract_job_highlights(job: Dict[str, Any], limit: int = 3) -> list[str]:
    text = job_text(job)
    keywords = {keyword.lower() for keyword in extract_job_keywords(job, limit=20)}
    candidates = [line.strip(" *-") for line in re.split(r"[\r\n]+", text) if line.strip()]
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        lowered = candidate.lower()
        if len(lowered) < 20:
            continue
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score:
            scored.append((score, _normalize_text(candidate)))
    if not scored:
        for candidate in candidates:
            cleaned = _normalize_text(candidate)
            if len(cleaned) >= 20:
                scored.append((0, cleaned))
    highlights: list[str] = []
    seen: set[str] = set()
    for _, candidate in sorted(scored, key=lambda item: (-item[0], len(item[1]))):
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        highlights.append(candidate[:180])
        if len(highlights) >= limit:
            break
    return highlights


def build_job_context(profile: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    skills = extract_profile_skills(profile)
    keywords = extract_job_keywords(job)
    focus_areas = extract_job_focus_areas(job)
    highlights = extract_job_highlights(job)
    return {
        "title": job.get("title") or "target role",
        "company": job.get("company") or "the company",
        "location": job.get("location") or "",
        "remote_type": job.get("remote_type") or "",
        "skills": skills,
        "keywords": keywords,
        "focus_areas": focus_areas,
        "highlights": highlights,
    }


def choose_primary_focus_area(focus_areas: list[str]) -> str:
    for area in focus_areas:
        if area != "AI / LLM workflows":
            return area
    return focus_areas[0] if focus_areas else "the role requirements"
