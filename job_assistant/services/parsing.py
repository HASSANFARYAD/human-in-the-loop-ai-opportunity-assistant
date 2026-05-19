from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Dict, List

import pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document

from .openai_client import ask_json

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\)\]\"']+")


def read_uploaded_cv(file) -> str:
    if file is None:
        return ""
    name = file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    return file.read().decode("utf-8", errors="ignore")


def clean_html(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text("\n")


def extract_job_from_text(raw: str, source: str = "Manual", opportunity_type: str = "job") -> Dict:
    text = clean_html(raw)
    urls = URL_RE.findall(text)
    emails = EMAIL_RE.findall(text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    fallback = {
        "title": lines[0][:120] if lines else "Untitled role",
        "company": "",
        "location": "",
        "remote_type": "Remote" if re.search(r"\bremote\b", text, re.I) else "",
        "url": urls[0] if urls else "",
        "source": source,
        "date_received": datetime.now(timezone.utc).date().isoformat(),
        "description": text[:8000],
        "recruiter_email": emails[0] if emails else "",
        "opportunity_type": opportunity_type,
        "raw_text": raw,
    }
    system = f"Extract a single {opportunity_type} opportunity into compact JSON. Return only JSON. Do not invent unknown fields."
    user = f"""
Fields: title, company, location, remote_type, url, source, date_received, description, recruiter_email, salary_min, salary_max, deadline, opportunity_type, raw_text.
Source is {source}. Text:\n{text[:12000]}
"""
    data = ask_json(system, user, fallback)
    for k, v in fallback.items():
        data.setdefault(k, v)
    data["source"] = source
    data["opportunity_type"] = opportunity_type
    data["raw_text"] = raw
    return data


def jobs_from_csv(uploaded_file, default_opportunity_type: str = "job") -> List[Dict]:
    df = pd.read_csv(uploaded_file)
    jobs = []
    for _, row in df.fillna("").iterrows():
        d = row.to_dict()
        jobs.append({
            "title": d.get("title") or d.get("Job title") or d.get("job_title") or "Untitled role",
            "company": d.get("company") or d.get("Company") or "",
            "location": d.get("location") or d.get("Location") or "",
            "remote_type": d.get("remote_type") or d.get("remote") or "",
            "url": d.get("url") or d.get("Job URL") or d.get("link") or "",
            "source": d.get("source") or "CSV",
            "date_received": d.get("date_received") or "",
            "description": d.get("description") or d.get("job_description") or "",
            "recruiter_email": d.get("recruiter_email") or "",
            "salary_min": d.get("salary_min") or None,
            "salary_max": d.get("salary_max") or None,
            "deadline": d.get("deadline") or "",
            "opportunity_type": (d.get("opportunity_type") or d.get("type") or default_opportunity_type or "job").lower(),
            "raw_text": str(d),
        })
    return jobs
