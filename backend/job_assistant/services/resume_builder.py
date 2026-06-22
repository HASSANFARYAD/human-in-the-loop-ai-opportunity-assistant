"""Render a structured resume into a country-standard DOCX document.

This module is pure rendering: it takes a normalized resume `structure` dict and
produces .docx bytes. The structure is produced upstream (AI-tailored to a job)
and is intentionally decoupled from how it gets generated.
"""

from __future__ import annotations

import io
from typing import Any


# Selectable country/region templates. Differences are mostly section labels,
# ordering, and which personal details are conventional to include.
RESUME_TEMPLATES: list[dict[str, str]] = [
    {"id": "us", "label": "United States (Resume)", "description": "1 page, no photo/DOB, action-verb bullets, reverse-chronological."},
    {"id": "uk", "label": "United Kingdom (CV)", "description": "Up to 2 pages, personal statement, no photo/DOB."},
    {"id": "eu", "label": "Europe (Europass-style)", "description": "Structured sections incl. personal information and skills."},
    {"id": "ca", "label": "Canada (Resume)", "description": "1–2 pages, no personal data, skills-forward."},
    {"id": "au", "label": "Australia (Resume)", "description": "2–3 pages, detailed experience and key skills."},
    {"id": "international", "label": "International (Generic)", "description": "Neutral, ATS-friendly layout."},
]

_TEMPLATE_IDS = {t["id"] for t in RESUME_TEMPLATES}

# The schema the AI layer should fill in to drive document rendering.
RESUME_STRUCTURE_KEYS = [
    "full_name",
    "headline",
    "contact",        # {email, phone, location, linkedin, website}
    "summary",
    "skills",         # [str]
    "experience",     # [{title, company, location, start, end, bullets:[str]}]
    "education",      # [{degree, institution, location, year}]
    "certifications", # [str]
    "projects",       # [{name, description}]
]


def is_valid_template(template: str) -> bool:
    return template in _TEMPLATE_IDS


def _summary_label(template: str) -> str:
    return {"uk": "Personal Statement", "eu": "Profile"}.get(template, "Professional Summary")


def _experience_label(template: str) -> str:
    return "Work Experience" if template == "eu" else "Experience"


def _education_label(template: str) -> str:
    return "Education and Training" if template == "eu" else "Education"


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _contact_line(contact: dict[str, Any], template: str) -> str:
    if not isinstance(contact, dict):
        return ""
    order = ["location", "phone", "email", "linkedin", "website"]
    parts = [str(contact.get(key)).strip() for key in order if str(contact.get(key) or "").strip()]
    return "  •  ".join(parts)


def render_resume_docx(structure: dict[str, Any], template: str = "international") -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    if not is_valid_template(template):
        template = "international"

    doc = Document()
    # Tighten default spacing for a clean one/two-page layout.
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    structure = structure or {}
    full_name = str(structure.get("full_name") or "Your Name").strip()
    headline = str(structure.get("headline") or "").strip()
    contact = structure.get("contact") or {}

    # Header: name (+ headline) and contact line.
    name_p = doc.add_paragraph()
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER if template in ("us", "ca", "international") else WD_ALIGN_PARAGRAPH.LEFT
    name_run = name_p.add_run(full_name)
    name_run.bold = True
    name_run.font.size = Pt(20)
    name_run.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

    if headline:
        h = doc.add_paragraph()
        h.alignment = name_p.alignment
        hr = h.add_run(headline)
        hr.italic = True
        hr.font.size = Pt(12)

    contact_line = _contact_line(contact, template)
    if contact_line:
        c = doc.add_paragraph()
        c.alignment = name_p.alignment
        c.add_run(contact_line).font.size = Pt(9.5)

    def section_heading(text: str) -> None:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        run = p.add_run(text.upper())
        run.bold = True
        run.font.size = Pt(11.5)
        run.font.color.rgb = RGBColor(0x29, 0x36, 0x46)
        # A bold uppercase heading reads cleanly across templates and ATS parsers.

    # EU/Europass convention leads with explicit personal information.
    if template == "eu" and isinstance(contact, dict):
        section_heading("Personal Information")
        for key in ("location", "phone", "email", "linkedin", "website"):
            val = str(contact.get(key) or "").strip()
            if val:
                doc.add_paragraph(f"{key.capitalize()}: {val}")

    summary = str(structure.get("summary") or "").strip()
    if summary:
        section_heading(_summary_label(template))
        doc.add_paragraph(summary)

    skills = [str(s).strip() for s in _as_list(structure.get("skills")) if str(s).strip()]
    if skills:
        section_heading("Skills")
        doc.add_paragraph("  •  ".join(skills))

    experience = _as_list(structure.get("experience"))
    if experience:
        section_heading(_experience_label(template))
        for role in experience:
            if not isinstance(role, dict):
                continue
            title = str(role.get("title") or "").strip()
            company = str(role.get("company") or "").strip()
            location = str(role.get("location") or "").strip()
            start = str(role.get("start") or "").strip()
            end = str(role.get("end") or "").strip()
            head = doc.add_paragraph()
            left = " — ".join(part for part in [title, company] if part)
            run = head.add_run(left)
            run.bold = True
            dates = " – ".join(part for part in [start, end] if part)
            meta = "  |  ".join(part for part in [location, dates] if part)
            if meta:
                head.add_run(f"   {meta}").italic = True
            for bullet in _as_list(role.get("bullets")):
                text = str(bullet).strip()
                if text:
                    doc.add_paragraph(text, style="List Bullet")

    education = _as_list(structure.get("education"))
    if education:
        section_heading(_education_label(template))
        for edu in education:
            if not isinstance(edu, dict):
                doc.add_paragraph(str(edu), style="List Bullet")
                continue
            degree = str(edu.get("degree") or "").strip()
            inst = str(edu.get("institution") or "").strip()
            year = str(edu.get("year") or "").strip()
            line = " — ".join(part for part in [degree, inst] if part)
            if year:
                line = f"{line} ({year})" if line else year
            if line:
                doc.add_paragraph(line, style="List Bullet")

    certifications = [str(c).strip() for c in _as_list(structure.get("certifications")) if str(c).strip()]
    if certifications:
        section_heading("Certifications")
        for cert in certifications:
            doc.add_paragraph(cert, style="List Bullet")

    projects = _as_list(structure.get("projects"))
    if projects:
        section_heading("Projects")
        for proj in projects:
            if isinstance(proj, dict):
                name = str(proj.get("name") or "").strip()
                desc = str(proj.get("description") or "").strip()
                p = doc.add_paragraph(style="List Bullet")
                if name:
                    p.add_run(f"{name}: ").bold = True
                if desc:
                    p.add_run(desc)
            else:
                doc.add_paragraph(str(proj), style="List Bullet")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
