from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Dict, List

from .openai_client import ask_json

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\)\]\"']+")
OPPORTUNITY_TYPES = {
    "job",
    "internship",
    "contract",
    "freelance",
    "hackathon",
    "competition",
    "grant",
    "scholarship",
    "webinar",
    "event",
    "newsletter",
    "blog_post",
    "marketing_email",
    "announcement",
    "unknown",
    "other",
}


def infer_opportunity_type(text: str, source: str = "") -> str:
    haystack = f"{source} {text}".lower()
    if any(word in haystack for word in ["internship", "intern ", "interns", "graduate program", "new grad"]):
        return "internship"
    if any(word in haystack for word in ["contract", "contractor"]):
        return "contract"
    if any(word in haystack for word in ["freelance", "freelancer"]):
        return "freelance"
    if any(word in haystack for word in ["hackathon", "devpost", "buildathon"]):
        return "hackathon"
    if any(word in haystack for word in ["scholarship"]):
        return "scholarship"
    if any(word in haystack for word in ["grant", "fellowship"]):
        return "grant"
    if any(word in haystack for word in ["webinar", "workshop", "seminar", "online event"]):
        return "webinar"
    if any(word in haystack for word in ["newsletter", "digest", "unsubscribe", "view in browser", "medium.com"]):
        return "newsletter"
    if any(word in haystack for word in ["blog", "article", "read more"]):
        return "blog_post"
    if any(word in haystack for word in ["announcing", "announcement", "product update", "new feature"]):
        return "announcement"
    if any(word in haystack for word in ["competition", "contest", "challenge", "championship"]):
        return "competition"
    if any(word in haystack for word in ["job", "role", "hiring", "recruiter", "apply", "career"]):
        return "job"
    return "other"


def is_unsupported_listing_url(raw: str) -> bool:
    text = raw.strip().lower()
    if not text.startswith(("http://", "https://")):
        return False
    listing_markers = [
        "linkedin.com/jobs/search",
        "linkedin.com/jobs/collections",
        "indeed.com/jobs",
        "indeed.com/q-",
        "devpost.com/hackathons",
    ]
    return any(marker in text for marker in listing_markers)


def unsupported_listing_message(raw: str) -> str:
    text = raw.strip().lower()
    if "linkedin.com/jobs/search" in text or "linkedin.com/jobs/collections" in text:
        return "LinkedIn search/listing URLs cannot be bulk-imported safely. Open individual jobs and paste each job description, use Gmail alerts, CSV import, or Public discovery."
    if "indeed.com" in text:
        return "Indeed listing URLs are not imported by direct scraping. Use Public discovery, Gmail alerts, CSV import, or paste individual job descriptions."
    if "devpost.com/hackathons" in text:
        return "Devpost listing pages are not bulk-scraped. Paste an individual hackathon page/description or import from an allowed public source."
    return "This looks like a listing/search URL. Paste an individual opportunity description or use Public discovery/Gmail/CSV import."


def read_uploaded_cv(file) -> str:
    if file is None:
        return ""
    name = file.name.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(file)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        from docx import Document

        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    return file.read().decode("utf-8", errors="ignore")


def clean_html(text: str) -> str:
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(text or "", "html.parser").get_text("\n")
    except ModuleNotFoundError:
        return re.sub(r"<[^>]+>", "\n", text or "")


# Characters that, when leading a spreadsheet cell, can trigger formula
# execution if the exported CSV is later opened in Excel/Sheets.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize_csv_formula(value: str) -> str:
    """Defang CSV/Excel formula injection by prefixing risky cells with a quote.

    A cell beginning with =, +, -, @ (or tab/CR) is treated as a formula by
    spreadsheet apps. Prefixing with a single quote forces it to be read as
    literal text. See https://owasp.org/www-community/attacks/CSV_Injection.
    """
    if not isinstance(value, str):
        return value
    if value and value.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def sanitize_imported_text(value, *, strip_html: bool = True, max_length: int | None = None):
    """Sanitize a free-text field arriving from an untrusted import source.

    Strips HTML/markup, removes control characters, neutralizes spreadsheet
    formula injection, and trims to ``max_length`` when given. Non-string
    values are returned unchanged.
    """
    if not isinstance(value, str):
        return value
    text = clean_html(value) if strip_html else value
    # Drop ASCII control chars except tab/newline/carriage-return.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = text.strip()
    if max_length is not None:
        text = text[:max_length]
    return neutralize_csv_formula(text)


def extract_profile_from_resume(cv_text: str, user_id: int | None = None) -> Dict:
    text = cv_text or ""
    fallback = _fallback_profile_from_resume(text)
    system = "Extract a job-search profile from a resume. Return only compact JSON. Do not invent missing facts."
    user = f"""
Return JSON fields:
cv_text, target_roles, industries, locations, remote_preference, salary_expectations,
work_authorization, years_experience, skills, deal_breakers.

Rules:
- target_roles should be comma-separated likely target job titles based on resume experience.
- industries should be comma-separated likely industries/domains from the resume.
- locations should include explicit locations only.
- remote_preference should be Remote/Hybrid/On-site only if clearly stated, otherwise blank.
- salary_expectations, work_authorization, and deal_breakers should stay blank unless explicitly present.
- skills should be concise comma-separated skills.

RESUME:
{text[:16000]}
"""
    data = ask_json(system, user, fallback, user_id=user_id, task_type="opportunity_parsing")
    for key, value in fallback.items():
        if not data.get(key):
            data[key] = value
    data["cv_text"] = text
    return _sanitize_profile_from_resume(data, fallback, text)


def _sanitize_profile_from_resume(data: Dict, fallback: Dict, text: str) -> Dict:
    out = dict(data)
    out["locations"] = _clean_locations(str(out.get("locations", "")), fallback.get("locations", ""))
    out["years_experience"] = _clean_years(str(out.get("years_experience", "")), fallback.get("years_experience", ""))
    out["skills"] = _clean_skills(str(out.get("skills", "")), fallback.get("skills", ""))

    for field in ["salary_expectations", "work_authorization", "deal_breakers"]:
        if out.get(field) and not _field_is_explicit_in_resume(str(out[field]), text):
            out[field] = fallback.get(field, "")
    return out


def _fallback_profile_from_resume(text: str) -> Dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    skills = _extract_skills(text, lines)
    target_roles = _extract_target_roles(text, lines)
    locations = _extract_locations(text)
    years = _extract_years_experience(text)
    industries = _extract_industries(text)
    remote = "Remote" if re.search(r"\bremote\b", text, re.I) else "Hybrid" if re.search(r"\bhybrid\b", text, re.I) else ""
    return {
        "cv_text": text,
        "target_roles": target_roles,
        "industries": industries,
        "locations": locations,
        "remote_preference": remote,
        "salary_expectations": "",
        "work_authorization": _extract_work_authorization(text),
        "years_experience": years,
        "skills": skills,
        "deal_breakers": "",
    }


def _extract_skills(text: str, lines: list[str]) -> str:
    skill_section = _section_text(lines, ["skills", "technical skills", "technologies"], ["experience", "work experience", "education", "projects"])
    source = skill_section or text
    known = [
        "Python", "JavaScript", "TypeScript", "Java", "C#", "C++", "SQL", "PostgreSQL", "MySQL",
        "React", "Next.js", "Node.js", "FastAPI", "Django", "Flask", "Docker",
        "Kubernetes", "AWS", "Azure", "GCP", "Terraform", "Git", "Pandas", "NumPy", "Spark",
        "Airflow", "Machine Learning", "Deep Learning", "NLP", "LLM", "OpenAI", "LangChain",
        "Data Engineering", "Data Analysis", "Power BI", "Tableau", "Project Management",
        "Agile", "Scrum", "Jira",
    ]
    found = []
    for skill in known:
        if re.search(rf"(?<![A-Za-z0-9+#.]){re.escape(skill)}(?![A-Za-z0-9+#.])", source, re.I):
            found.append(skill)
    if found:
        return ", ".join(dict.fromkeys(found))
    if skill_section:
        cleaned = re.sub(r"\s*[|;]\s*", ", ", skill_section)
        return ", ".join(part.strip(" -•") for part in re.split(r",|\n", cleaned) if part.strip())[:500]
    return ""


def _extract_target_roles(text: str, lines: list[str]) -> str:
    title_patterns = [
        "Data Engineer", "Software Engineer", "Backend Engineer", "Frontend Engineer", "Full Stack Engineer",
        "Machine Learning Engineer", "AI Engineer", "Data Scientist", "Data Analyst", "Project Manager",
        "Product Manager", "Business Analyst", "DevOps Engineer", "Cloud Engineer", "QA Engineer",
    ]
    found = [role for role in title_patterns if re.search(rf"\b{re.escape(role)}\b", text, re.I)]
    if found:
        return ", ".join(dict.fromkeys(found[:4]))
    for line in lines[:12]:
        if 3 <= len(line.split()) <= 8 and not EMAIL_RE.search(line) and not URL_RE.search(line):
            if any(word in line.lower() for word in ["engineer", "developer", "manager", "analyst", "scientist", "consultant"]):
                return line[:120]
    return ""


def _extract_locations(text: str) -> str:
    explicit = re.search(r"(?:location|address)\s*[:\-]\s*([^\n|•]+)", text, re.I)
    if explicit:
        return _clean_locations(explicit.group(1), "")

    countries = [
        "Pakistan", "United States", "United Kingdom", "Canada", "Australia", "Germany", "France",
        "Netherlands", "United Arab Emirates", "Saudi Arabia", "India",
    ]
    cities = [
        "Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Austin", "New York",
        "San Francisco", "London", "Manchester", "Toronto", "Dubai", "Berlin",
    ]
    found = []
    for place in [*cities, *countries]:
        if re.search(rf"\b{re.escape(place)}\b", text, re.I):
            found.append(place)
    city_country = re.findall(r"\b([A-Z][a-zA-Z]+,\s*(?:[A-Z]{2}|[A-Z][a-zA-Z]+))\b", text)
    found.extend(city_country)
    return _clean_locations(", ".join(dict.fromkeys(found[:5])), "")


def _extract_years_experience(text: str) -> str:
    matches = [int(value) for value in re.findall(r"(\d+)\+?\s*(?:years|yrs)", text, re.I)]
    if matches:
        return f"{max(matches)} years"
    inferred = _infer_years_from_date_ranges(text)
    if inferred:
        return f"{inferred} years"
    return ""


def _infer_years_from_date_ranges(text: str) -> int:
    from datetime import datetime

    month_names = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
    pattern = re.compile(
        rf"(?:(?:{month_names})\s+)?(20\d{{2}}|19\d{{2}})\s*(?:-|–|—|to)\s*(?:(?:{month_names})\s+)?(present|current|now|20\d{{2}}|19\d{{2}})",
        re.I,
    )
    total_months = 0
    current_year = datetime.now().year
    for start, end in pattern.findall(text):
        start_year = int(start)
        end_year = current_year if end.lower() in {"present", "current", "now"} else int(end)
        if end_year >= start_year and 1980 <= start_year <= current_year:
            total_months += max(0, (end_year - start_year) * 12)
    if not total_months:
        return 0
    return max(1, round(total_months / 12))


def _extract_industries(text: str) -> str:
    known = ["Fintech", "Healthcare", "E-commerce", "SaaS", "Education", "Cybersecurity", "AI", "Banking", "Retail", "Logistics", "Real Estate"]
    found = [industry for industry in known if re.search(rf"\b{re.escape(industry)}\b", text, re.I)]
    return ", ".join(dict.fromkeys(found[:5]))


def _extract_work_authorization(text: str) -> str:
    patterns = [
        r"authorized to work[^.\n]*",
        r"work authorization[^.\n]*",
        r"citizen(?:ship)?[^.\n]*",
        r"permanent resident[^.\n]*",
        r"visa[^.\n]*",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0).strip()
    return ""


def _section_text(lines: list[str], headers: list[str], stop_headers: list[str]) -> str:
    capture = False
    collected: list[str] = []
    for line in lines:
        normalized = line.strip().lower().rstrip(":")
        if normalized in headers:
            capture = True
            continue
        if capture and normalized in stop_headers:
            break
        if capture:
            collected.append(line)
    return "\n".join(collected).strip()


def _clean_locations(value: str, fallback: str) -> str:
    tech_terms = {
        "sass", "less", "javascript", "typescript", "html", "css", "sql", "studio", "git", "react",
        "python", "docker", "postgresql", "mysql", "node", "java", "c#", "c++", "api", "aws",
    }
    parts = [part.strip(" .;|•") for part in re.split(r",|\n|;", value or "") if part.strip()]
    cleaned = []
    for part in parts:
        lower = part.lower()
        if lower in tech_terms:
            continue
        if any(term in lower.split() for term in tech_terms):
            continue
        if re.search(r"\d", part) and not re.search(r"\b[A-Z]{2}\b", part):
            continue
        if len(part) > 40:
            continue
        if re.search(r"\b(remote|hybrid|onsite|on-site)\b", part, re.I):
            continue
        if re.search(r"\b(pakistan|united states|united kingdom|canada|australia|germany|france|india|uae|dubai|lahore|karachi|islamabad|london|toronto|new york|austin|berlin)\b", part, re.I) or re.search(r"^[A-Z][a-zA-Z ]+,\s*(?:[A-Z]{2}|[A-Z][a-zA-Z ]+)$", part):
            cleaned.append(part)
    result = ", ".join(dict.fromkeys(cleaned))
    return result or fallback


def _clean_years(value: str, fallback: str) -> str:
    if re.search(r"\b\d+\+?\s*(?:years|yrs)\b", value, re.I):
        number = re.search(r"\d+", value)
        return f"{number.group(0)} years" if number else value
    if value.strip().isdigit():
        return f"{value.strip()} years"
    return fallback


def _clean_skills(value: str, fallback: str) -> str:
    parts = [part.strip(" .;|•") for part in re.split(r",|\n|;", value or "") if part.strip()]
    bad_location_terms = {"lahore", "pakistan", "united states", "united kingdom", "canada", "australia"}
    cleaned = [part for part in parts if part.lower() not in bad_location_terms and len(part) <= 40]
    result = ", ".join(dict.fromkeys(cleaned))
    return result or fallback


def _field_is_explicit_in_resume(value: str, text: str) -> bool:
    if not value.strip():
        return False
    normalized_value = re.sub(r"\s+", " ", value).strip().lower()
    normalized_text = re.sub(r"\s+", " ", text).strip().lower()
    if normalized_value in normalized_text:
        return True
    return any(token in normalized_text for token in normalized_value.split(",")[:2] if len(token.strip()) > 5)


def extract_job_from_text(raw: str, source: str = "Manual", opportunity_type: str = "job", user_id: int | None = None) -> Dict:
    from job_assistant.services.opportunity_classifier import annotate_opportunity

    text = clean_html(raw)
    if opportunity_type == "auto":
        opportunity_type = infer_opportunity_type(text, source)
    opportunity_type = opportunity_type if opportunity_type in OPPORTUNITY_TYPES else "other"
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
    data = ask_json(system, user, fallback, user_id=user_id, task_type="opportunity_parsing")
    for k, v in fallback.items():
        data.setdefault(k, v)
    data["source"] = source
    data["opportunity_type"] = opportunity_type
    data["raw_text"] = raw
    return annotate_opportunity(data, source=source)


def jobs_from_csv(uploaded_file, default_opportunity_type: str = "job") -> List[Dict]:
    import pandas as pd

    df = pd.read_csv(uploaded_file, dtype=str)
    jobs = []
    for _, row in df.fillna("").iterrows():
        d = row.to_dict()

        def field(*keys, max_length: int | None = 2000):
            for key in keys:
                value = d.get(key)
                if value:
                    return sanitize_imported_text(str(value), max_length=max_length)
            return ""

        jobs.append({
            "title": field("title", "Job title", "job_title", max_length=300) or "Untitled role",
            "company": field("company", "Company", max_length=300),
            "location": field("location", "Location", max_length=300),
            "remote_type": field("remote_type", "remote", max_length=100),
            "url": field("url", "Job URL", "link", max_length=2000),
            "source": field("source", max_length=100) or "CSV",
            "date_received": field("date_received", max_length=100),
            "description": field("description", "job_description", max_length=20000),
            "recruiter_email": field("recruiter_email", max_length=320),
            "salary_min": d.get("salary_min") or None,
            "salary_max": d.get("salary_max") or None,
            "deadline": field("deadline", max_length=100),
            "opportunity_type": (field("opportunity_type", "type", max_length=50) or default_opportunity_type or "job").lower(),
            "classification": (field("classification", "opportunity_type", "type", max_length=50) or default_opportunity_type or "job").lower(),
            "classification_confidence": field("classification_confidence", max_length=50),
            "classification_reason": field("classification_reason", max_length=500),
            "opportunity_confidence": field("opportunity_confidence", max_length=50),
            "raw_text": str(d),
        })
    return jobs
