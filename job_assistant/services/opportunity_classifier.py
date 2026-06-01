from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from job_assistant.services.parsing import URL_RE, clean_html

VALID_OPPORTUNITY_CATEGORIES = {
    "job",
    "internship",
    "contract",
    "freelance",
    "competition",
    "hackathon",
    "grant",
    "scholarship",
}
NON_OPPORTUNITY_CATEGORIES = {
    "newsletter",
    "blog_post",
    "marketing_email",
    "announcement",
    "webinar",
    "event",
    "unknown",
}
SUPPORTED_CLASSIFICATIONS = VALID_OPPORTUNITY_CATEGORIES | NON_OPPORTUNITY_CATEGORIES

JOB_EVIDENCE = (
    "apply now",
    "apply for this",
    "job description",
    "responsibilities",
    "requirements",
    "qualifications",
    "we are hiring",
    "we're hiring",
    "is hiring",
    "hiring for",
    "open role",
    "open position",
    "full-time",
    "part-time",
    "contract role",
    "recruiter",
    "salary",
)
OPPORTUNITY_EVIDENCE = (
    "deadline",
    "eligibility",
    "application",
    "submit your application",
    "prize",
    "grant",
    "scholarship",
    "fellowship",
    "hackathon",
    "competition",
    "challenge",
)
CONTAINER_EVIDENCE = (
    "newsletter",
    "digest",
    "roundup",
    "weekly",
    "unsubscribe",
    "view in browser",
    "medium digest",
    "substack",
)
BLOG_EVIDENCE = ("blog", "article", "read more", "posted by", "medium.com", "towardsdatascience.com")
MARKETING_EVIDENCE = ("product update", "launch", "announcing", "new feature", "partner program", "promotion")
EVENT_EVIDENCE = ("webinar", "event", "workshop", "seminar", "meetup", "register now")
TRACKING_HOST_PARTS = ("sendgrid.net", "list-manage.com", "mailchi.mp", "mandrillapp.com", "sparkpostmail.com")


@dataclass
class ClassificationResult:
    classification: str
    confidence: float
    opportunity_confidence: float
    importable: bool
    reason: str
    extracted_opportunities_count: int = 0
    evidence_count: int = 0
    blocked_reason: str = ""
    links: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "classification_confidence": self.confidence,
            "opportunity_confidence": self.opportunity_confidence,
            "importable": self.importable,
            "classification_reason": self.reason,
            "blocked_reason": self.blocked_reason,
            "extracted_opportunities_count": self.extracted_opportunities_count,
            "evidence_count": self.evidence_count,
            "links": self.links,
        }


def normalize_url(url: str) -> str:
    value = (url or "").strip().rstrip(".,);]")
    if not value:
        return ""
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if any(part in host for part in TRACKING_HOST_PARTS):
        query = parse_qs(parsed.query)
        for key in ("url", "u", "target", "redirect", "redirect_url"):
            if query.get(key):
                return unquote(query[key][0])
    return value


def extract_links(text: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    for raw_url in URL_RE.findall(text or ""):
        normalized = normalize_url(raw_url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        links.append({"original_url": raw_url, "resolved_url": normalized})
    return links


def classify_source_item(item: dict[str, Any] | str, *, source: str = "") -> ClassificationResult:
    if isinstance(item, str):
        title = ""
        text = item
        url = ""
    else:
        title = str(item.get("title") or item.get("subject") or "")
        text = " ".join(
            str(item.get(key) or "")
            for key in ["title", "company", "source", "description", "raw_text", "snippet", "body", "url"]
        )
        url = str(item.get("url") or "")
        source = source or str(item.get("source") or "")
    cleaned = clean_html(text)
    haystack = f"{title} {source} {cleaned} {url}".lower()
    links = extract_links(cleaned)

    job_hits = _count_hits(haystack, JOB_EVIDENCE)
    opp_hits = _count_hits(haystack, OPPORTUNITY_EVIDENCE)
    container_hits = _count_hits(haystack, CONTAINER_EVIDENCE)
    blog_hits = _count_hits(haystack, BLOG_EVIDENCE)
    marketing_hits = _count_hits(haystack, MARKETING_EVIDENCE)
    event_hits = _count_hits(haystack, EVENT_EVIDENCE)
    has_apply_url = bool(url and _url_looks_applyable(url)) or any(_url_looks_applyable(link["resolved_url"]) for link in links)
    subject_container = title.lower().startswith("subject:") or haystack.startswith("subject:")

    classification = "unknown"
    reason = "No strong opportunity evidence was detected."
    if "internship" in haystack or re.search(r"\bintern\b", haystack):
        classification = "internship"
        reason = "Internship terms were detected."
    elif "hackathon" in haystack or "devpost" in haystack or "buildathon" in haystack:
        classification = "hackathon"
        reason = "Hackathon terms were detected."
    elif "scholarship" in haystack:
        classification = "scholarship"
        reason = "Scholarship terms were detected."
    elif "grant" in haystack or "fellowship" in haystack:
        classification = "grant"
        reason = "Grant or fellowship terms were detected."
    elif "freelance" in haystack:
        classification = "freelance"
        reason = "Freelance opportunity terms were detected."
    elif "contract" in haystack and job_hits:
        classification = "contract"
        reason = "Contract role terms were detected."
    elif "competition" in haystack or "contest" in haystack or "challenge" in haystack:
        classification = "competition"
        reason = "Competition terms were detected."
    elif job_hits >= 2 or (job_hits >= 1 and has_apply_url):
        classification = "job"
        reason = "Job evidence and an application/source signal were detected."

    if classification == "unknown":
        if event_hits:
            classification = "webinar" if "webinar" in haystack else "event"
            reason = "Event/webinar terms were detected without application opportunity evidence."
        elif blog_hits:
            classification = "blog_post"
            reason = "Article/blog content was detected without job evidence."
        elif container_hits:
            classification = "newsletter"
            reason = "Newsletter/digest markers were detected."
        elif marketing_hits:
            classification = "announcement"
            reason = "Announcement or promotional content was detected."

    if classification in VALID_OPPORTUNITY_CATEGORIES and (container_hits + blog_hits + marketing_hits) > job_hits + opp_hits:
        classification = "newsletter" if container_hits else "blog_post"
        reason = "Container/content markers outweighed opportunity evidence."

    evidence_count = job_hits + opp_hits + int(has_apply_url)
    opportunity_confidence = min(0.98, 0.2 + evidence_count * 0.18)
    classification_confidence = 0.9 if classification in NON_OPPORTUNITY_CATEGORIES else min(0.95, 0.55 + evidence_count * 0.12)
    importable = classification in VALID_OPPORTUNITY_CATEGORIES and validate_opportunity_payload(
        {"title": title, "description": cleaned, "url": url, "source": source, "opportunity_type": classification}
    ).importable
    blocked_reason = "" if importable else _blocked_reason(classification, subject_container, evidence_count)

    return ClassificationResult(
        classification=classification,
        confidence=round(classification_confidence, 2),
        opportunity_confidence=round(opportunity_confidence if importable else min(opportunity_confidence, 0.45), 2),
        importable=importable,
        reason=reason,
        evidence_count=evidence_count,
        blocked_reason=blocked_reason,
        links=links,
    )


def validate_opportunity_payload(item: dict[str, Any]) -> ClassificationResult:
    classification = str(item.get("classification") or item.get("opportunity_type") or "unknown").lower()
    if classification not in SUPPORTED_CLASSIFICATIONS:
        classification = "unknown"
    text = " ".join(str(item.get(key) or "") for key in ["title", "company", "description", "raw_text", "url", "source"]).lower()
    title = str(item.get("title") or "").strip()
    company = str(item.get("company") or "").strip()
    description = str(item.get("description") or item.get("raw_text") or "").strip()
    url = str(item.get("url") or "").strip()
    evidence = 0
    evidence += 1 if title and not title.lower().startswith("subject:") else 0
    evidence += 1 if company and company.lower() not in {"unknown", "unknown company"} else 0
    evidence += 1 if len(description) >= 120 else 0
    evidence += 1 if _count_hits(text, JOB_EVIDENCE) or _count_hits(text, OPPORTUNITY_EVIDENCE) else 0
    evidence += 1 if url and _url_looks_applyable(url) else 0
    confidence = min(0.98, 0.2 + evidence * 0.18)
    subject_container = title.lower().startswith("subject:") or str(item.get("source") or "").lower() == "gmail"
    importable = classification in VALID_OPPORTUNITY_CATEGORIES and evidence >= 3 and not (subject_container and not company)
    return ClassificationResult(
        classification=classification,
        confidence=round(max(0.5, confidence), 2),
        opportunity_confidence=round(confidence if importable else min(confidence, 0.45), 2),
        importable=importable,
        reason=f"{evidence} opportunity evidence signals detected.",
        evidence_count=evidence,
        blocked_reason="" if importable else _blocked_reason(classification, subject_container, evidence),
        links=extract_links(description),
    )


def annotate_opportunity(item: dict[str, Any], *, source: str = "") -> dict[str, Any]:
    annotated = dict(item)
    classification = classify_source_item(annotated, source=source)
    validation = validate_opportunity_payload({**annotated, "classification": classification.classification})
    annotated.update(classification.as_dict())
    annotated["classification"] = classification.classification
    annotated["opportunity_type"] = (
        annotated.get("opportunity_type")
        if annotated.get("opportunity_type") in VALID_OPPORTUNITY_CATEGORIES
        else classification.classification
    )
    annotated["importable"] = validation.importable
    annotated["opportunity_confidence"] = validation.opportunity_confidence
    annotated["blocked_reason"] = validation.blocked_reason
    return annotated


def extract_opportunities_from_container(item: dict[str, Any]) -> list[dict[str, Any]]:
    text = clean_html(" ".join(str(item.get(key) or "") for key in ["subject", "title", "snippet", "body", "description", "raw_text"]))
    source_title = str(item.get("subject") or item.get("title") or "").strip()
    source_url = str(item.get("open_url") or item.get("source_url") or item.get("url") or "").strip()
    links = extract_links(text)
    opportunities: list[dict[str, Any]] = []
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        window = "\n".join(lines[max(0, index - 1): index + 4])
        if _count_hits(window.lower(), JOB_EVIDENCE + OPPORTUNITY_EVIDENCE) < 2:
            continue
        link = next((entry["resolved_url"] for entry in links if entry["resolved_url"] in window), "")
        candidate = {
            "title": line[:120],
            "company": "",
            "location": "",
            "remote_type": "Remote" if re.search(r"\bremote\b", window, re.I) else "",
            "url": link,
            "source": item.get("source") or "Gmail",
            "description": window[:4000],
            "raw_text": window,
            "source_type": item.get("source_type") or "container",
            "source_name": item.get("source_name") or item.get("sender") or "",
            "source_url": source_url,
            "source_email_id": item.get("message_id") or "",
            "source_email_open_url": item.get("open_url") or "",
            "parent_source_title": source_title,
            "extracted_from": source_title or source_url,
            "raw_source_snippet": str(item.get("snippet") or text[:500]),
        }
        annotated = annotate_opportunity(candidate)
        if annotated.get("importable"):
            opportunities.append(annotated)

    for link in links:
        url = link["resolved_url"]
        if not _url_looks_applyable(url):
            continue
        title = _title_from_url(url)
        candidate = {
            "title": title,
            "company": "",
            "url": url,
            "source": item.get("source") or "Gmail",
            "description": f"Opportunity link extracted from {source_title or 'source content'}: {url}",
            "raw_text": text[:4000],
            "source_type": item.get("source_type") or "container",
            "source_name": item.get("source_name") or item.get("sender") or "",
            "source_url": source_url,
            "source_email_id": item.get("message_id") or "",
            "source_email_open_url": item.get("open_url") or "",
            "parent_source_title": source_title,
            "extracted_from": source_title or source_url,
            "raw_source_snippet": str(item.get("snippet") or text[:500]),
        }
        annotated = annotate_opportunity(candidate)
        if annotated.get("importable"):
            opportunities.append(annotated)

    unique: dict[str, dict[str, Any]] = {}
    for opportunity in opportunities:
        key = opportunity.get("url") or f"{opportunity.get('title')}|{opportunity.get('description')[:80]}"
        unique.setdefault(str(key), opportunity)
    return list(unique.values())


def scoring_gate(job: dict[str, Any]) -> ClassificationResult:
    return validate_opportunity_payload({**job, "classification": job.get("classification") or job.get("opportunity_type")})


def _count_hits(text: str, needles: tuple[str, ...]) -> int:
    return sum(1 for needle in needles if needle in text)


def _url_looks_applyable(url: str) -> bool:
    value = normalize_url(url).lower()
    if not value.startswith(("http://", "https://")):
        return False
    host = urlparse(value).netloc
    if any(part in host for part in TRACKING_HOST_PARTS):
        return False
    blocked = ("medium.com", "substack.com", "youtube.com", "youtu.be", "mailchi.mp")
    if any(part in host for part in blocked):
        return False
    return any(part in value for part in ("/job", "jobs.", "/careers", "/career", "/apply", "greenhouse.io", "lever.co", "workable.com", "ashbyhq.com", "devpost.com", "scholarship", "grant", "competition", "hackathon"))


def _blocked_reason(classification: str, subject_container: bool, evidence_count: int) -> str:
    if classification in NON_OPPORTUNITY_CATEGORIES:
        return f"{classification.replace('_', ' ')} is not importable as a scored opportunity."
    if subject_container:
        return "Email subject/container content needs extracted opportunity evidence before import."
    return f"Only {evidence_count} opportunity evidence signal(s) detected; needs review."


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    label = parts[-1] if parts else parsed.netloc
    label = re.sub(r"[-_]+", " ", label)
    return label.strip().title()[:120] or "Extracted opportunity"
