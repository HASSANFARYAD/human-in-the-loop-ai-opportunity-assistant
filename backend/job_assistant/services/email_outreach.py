from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

from job_assistant.config import settings
from job_assistant.db import get_collection, utc_now, _next_id

logger = logging.getLogger(__name__)

EMAIL_TEMPLATES_COLLECTION = "email_templates"
EMAIL_OUTREACH_COLLECTION = "email_outreach"

DEFAULT_TEMPLATES = [
    {
        "name": "Standard Application",
        "subject": "Application for {job_title} position",
        "body": (
            "Dear Hiring Manager,\n\n"
            "I am writing to express my interest in the {job_title} position at {company_name}. "
            "I have attached my resume for your review.\n\n"
            "My background in {skill_area} aligns well with the requirements of this role. "
            "I would welcome the opportunity to discuss how my experience can contribute to your team.\n\n"
            "Thank you for your time and consideration.\n\n"
            "Best regards,\n{full_name}\n{email}\n{phone}"
        ),
        "is_default": True,
    },
    {
        "name": "Short & Direct",
        "subject": "Interest in {job_title} role",
        "body": (
            "Hi {recruiter_name or \"there\"},\n\n"
            "I came across the {job_title} opening at {company_name} and would love to be considered.\n\n"
            "My resume is attached. I'm confident my experience in {skill_area} would be a great fit.\n\n"
            "Looking forward to hearing from you.\n\n"
            "{full_name}\n{email}"
        ),
        "is_default": False,
    },
    {
        "name": "Networking Outreach",
        "subject": "Quick question about working at {company_name}",
        "body": (
            "Hi {recruiter_name or \"there\"},\n\n"
            "I've been following {company_name}'s work in {industry} and I'm very impressed. "
            "I am exploring opportunities in {skill_area} and would love to learn more about your team's work.\n\n"
            "Would you have 10 minutes for a brief chat this week?\n\n"
            "Best,\n{full_name}"
        ),
        "is_default": False,
    },
]


def ensure_default_templates(user_id: int) -> None:
    existing = list(get_collection(EMAIL_TEMPLATES_COLLECTION).find({"user_id": user_id}))
    if existing:
        return
    for tpl in DEFAULT_TEMPLATES:
        tpl["user_id"] = user_id
        tpl["template_id"] = _next_id("email_template_id")
        tpl["created_at"] = utc_now()
        tpl["updated_at"] = utc_now()
        get_collection(EMAIL_TEMPLATES_COLLECTION).insert_one(tpl)


def list_templates(user_id: int) -> list[dict[str, Any]]:
    rows = get_collection(EMAIL_TEMPLATES_COLLECTION).find({"user_id": user_id}).sort("created_at", 1)
    result = []
    for r in rows:
        r["id"] = r["_id"]
        result.append(r)
    return result


def create_template(user_id: int, name: str, subject: str, body: str, is_default: bool = False) -> int:
    tpl_id = _next_id("email_template_id")
    doc = {
        "_id": tpl_id,
        "user_id": user_id,
        "name": name,
        "subject": subject,
        "body": body,
        "is_default": is_default,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    get_collection(EMAIL_TEMPLATES_COLLECTION).insert_one(doc)
    return tpl_id


def update_template(user_id: int, template_id: int, **updates: Any) -> bool:
    updates["updated_at"] = utc_now()
    result = get_collection(EMAIL_TEMPLATES_COLLECTION).update_one(
        {"_id": template_id, "user_id": user_id},
        {"$set": updates},
    )
    return result.modified_count > 0


def delete_template(user_id: int, template_id: int) -> bool:
    result = get_collection(EMAIL_TEMPLATES_COLLECTION).delete_one(
        {"_id": template_id, "user_id": user_id},
    )
    return result.deleted_count > 0


# ── Email finder (recruiter email discovery) ──────────────────────────────


def find_recruiter_email(company_name: str, domain_hint: str = "") -> str:
    if domain_hint:
        patterns = [
            f"hr@{domain_hint}",
            f"careers@{domain_hint}",
            f"jobs@{domain_hint}",
            f"recruiting@{domain_hint}",
            f"talent@{domain_hint}",
        ]
        return patterns[0]

    try:
        search_url = f"https://www.google.com/search?q={company_name}+recruiter+email+OR+careers+email"
        resp = requests.get(
            search_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            },
            timeout=10,
        )
        email_pattern = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        emails = email_pattern.findall(resp.text)
        priority = ["hr", "careers", "jobs", "recruiting", "talent", "hiring", "recruiter"]
        for keyword in priority:
            for e in emails:
                if keyword.lower() in e.lower():
                    return e
        if emails:
            return emails[0]
    except Exception as e:
        logger.warning("Email search failed for %s: %s", company_name, e)

    return ""


# ── Email outreach send ───────────────────────────────────────────────────


@dataclass
class OutreachResult:
    success: bool
    message_id: str
    error: str = ""


def render_template(template: dict[str, Any], variables: dict[str, str]) -> tuple[str, str]:
    subject = template.get("subject", "")
    body = template.get("body", "")
    for key, value in variables.items():
        placeholder = "{" + key + "}"
        subject = subject.replace(placeholder, str(value))
        body = body.replace(placeholder, str(value))
    return subject, body


def send_outreach_email(
    user_id: int,
    job_id: int,
    template_id: int,
    to_email: str,
    variables: dict[str, str],
    workspace_id: int | None = None,
) -> OutreachResult:
    template = get_collection(EMAIL_TEMPLATES_COLLECTION).find_one(
        {"_id": template_id, "user_id": user_id},
    )
    if not template:
        return OutreachResult(success=False, message_id="", error="Template not found")

    subject, body = render_template(template, variables)
    outreach_id = _next_id("email_outreach_id")

    record = {
        "_id": outreach_id,
        "user_id": user_id,
        "job_id": job_id,
        "template_id": template_id,
        "template_name": template.get("name", ""),
        "to_email": to_email,
        "subject": subject,
        "body": body,
        "status": "queued",
        "sent_at": None,
        "opened_at": None,
        "replied_at": None,
        "error_message": "",
        "workspace_id": workspace_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }

    if settings.smtp_host and settings.smtp_from_email:
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.smtp_from_email
            msg["To"] = to_email
            msg.set_content(body)

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)

            record["status"] = "sent"
            record["sent_at"] = utc_now()
            get_collection(EMAIL_OUTREACH_COLLECTION).insert_one(record)
            return OutreachResult(success=True, message_id=str(outreach_id))
        except Exception as e:
            record["status"] = "failed"
            record["error_message"] = str(e)
            get_collection(EMAIL_OUTREACH_COLLECTION).insert_one(record)
            return OutreachResult(success=False, message_id=str(outreach_id), error=str(e))

    record["status"] = "simulated"
    get_collection(EMAIL_OUTREACH_COLLECTION).insert_one(record)
    logger.info("Email outreach captured (no SMTP): to=%s subject=%s", to_email, subject)
    return OutreachResult(success=True, message_id=str(outreach_id))


def list_outreach(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    rows = get_collection(EMAIL_OUTREACH_COLLECTION).find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    result = []
    for r in rows:
        r["id"] = r["_id"]
        result.append(r)
    return result


def get_outreach_stats(user_id: int) -> dict[str, Any]:
    coll = get_collection(EMAIL_OUTREACH_COLLECTION)
    total = coll.count_documents({"user_id": user_id})
    sent = coll.count_documents({"user_id": user_id, "status": "sent"})
    opened = coll.count_documents({"user_id": user_id, "opened_at": {"$ne": None}})
    replied = coll.count_documents({"user_id": user_id, "replied_at": {"$ne": None}})
    failed = coll.count_documents({"user_id": user_id, "status": "failed"})
    return {
        "total": total,
        "sent": sent,
        "opened": opened,
        "replied": replied,
        "failed": failed,
        "open_rate": round(opened / sent * 100, 1) if sent else 0,
        "reply_rate": round(replied / sent * 100, 1) if sent else 0,
    }
