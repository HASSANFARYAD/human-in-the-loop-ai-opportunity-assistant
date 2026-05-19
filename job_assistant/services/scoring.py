from __future__ import annotations

import re
from typing import Any, Dict

from .openai_client import ask_json


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#-]{1,}", s or "")}


def _years_experience(profile: Dict[str, Any]) -> int:
    match = re.search(r"\d+", str(profile.get("years_experience", "") or "0"))
    return int(match.group(0)) if match else 0


def _score_job_opportunity(profile: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """Score traditional job opportunities"""
    cv_skills = _tokens(" ".join(str(profile.get(k, "")) for k in ["cv_text", "skills", "target_roles", "industries"]))
    job_tokens = _tokens(" ".join(str(job.get(k, "")) for k in ["title", "company", "description", "location", "remote_type"]))
    skill_overlap = cv_skills & job_tokens
    skill_match = min(25, len(skill_overlap) * 3)

    title_tokens = _tokens(profile.get("target_roles", ""))
    title_match = 15 if title_tokens & _tokens(job.get("title", "")) else 5

    years = re.findall(r"\d+\+?\s*(?:years|yrs)", str(job.get("description", "")), re.I)
    seniority_match = 15
    if "senior" in job.get("title", "").lower() and _years_experience(profile) < 5:
        seniority_match = 5

    location_match = 10
    pref = str(profile.get("remote_preference", "") + " " + profile.get("locations", "")).lower()
    job_loc = str(job.get("location", "") + " " + job.get("remote_type", "") + " " + job.get("description", "")).lower()
    if "remote" in pref and "remote" in job_loc:
        location_match = 15
    elif "on-site" in job_loc or "onsite" in job_loc:
        location_match = 4

    salary_match = 10
    salary_expect = str(profile.get("salary_expectations", ""))
    expected_nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{4,}", salary_expect)]
    if expected_nums and job.get("salary_max"):
        try:
            salary_match = 10 if float(job.get("salary_max")) >= min(expected_nums) else 3
        except Exception:
            pass

    industry_match = 8 if _tokens(profile.get("industries", "")) & job_tokens else 3

    auth_text = (str(profile.get("work_authorization", "")) + " " + str(job.get("description", ""))).lower()
    authorization_match = 10
    if "sponsorship not available" in auth_text or "no sponsorship" in auth_text:
        authorization_match = 0

    deal_breaker_penalty = 0
    deal_breakers = [x.strip().lower() for x in re.split(r";|\n", str(profile.get("deal_breakers", ""))) if x.strip()]
    jd_lower = str(job.get("description", "") + " " + job.get("remote_type", "")).lower()
    triggered = [d for d in deal_breakers if any(w in jd_lower for w in d.split()[:5])]
    if triggered:
        deal_breaker_penalty = 25

    raw_score = skill_match + title_match + seniority_match + location_match + salary_match + industry_match + authorization_match - deal_breaker_penalty
    score = max(0, min(100, int(raw_score)))
    priority = "High" if score >= 75 else "Medium" if score >= 55 else "Low" if score >= 35 else "Skip"
    if deal_breaker_penalty >= 25 or authorization_match == 0:
        priority = "Skip" if score < 60 else "Low"

    return {
        "match_score": score,
        "priority": priority,
        "skill_match": skill_match,
        "title_match": title_match,
        "seniority_match": seniority_match,
        "location_match": location_match,
        "salary_match": salary_match,
        "industry_match": industry_match,
        "authorization_match": authorization_match,
        "deal_breaker_penalty": deal_breaker_penalty,
        "good_fit": f"Overlapping signals: {', '.join(sorted(list(skill_overlap))[:15]) or 'limited explicit keyword overlap'}. Title/location scoring contributed strongly where applicable.",
        "weak_areas": "Review exact seniority, salary, and sponsorship requirements manually; some postings omit these details.",
        "red_flags": "Potential deal-breaker or work authorization issue detected." if deal_breaker_penalty or authorization_match == 0 else "No obvious red flags detected by local rules.",
        "opportunity_type": "job",
    }


def _score_hackathon(profile: Dict[str, Any], hackathon: Dict[str, Any]) -> Dict[str, Any]:
    """Score hackathon opportunities based on tech fit, prizes, and time availability"""
    cv_skills = _tokens(" ".join(str(profile.get(k, "")) for k in ["cv_text", "skills", "target_roles"]))
    hack_tokens = _tokens(" ".join(str(hackathon.get(k, "")) for k in ["title", "description"]))
    skill_overlap = cv_skills & hack_tokens
    tech_stack_match = min(30, len(skill_overlap) * 4)

    prize_pool_text = str(hackathon.get("description", "") + " " + hackathon.get("raw_text", "")).lower()
    prize_value_score = 15
    if any(word in prize_pool_text for word in ["$50000", "$100000", "$50k", "$100k", "50000", "100000"]):
        prize_value_score = 20
    elif any(word in prize_pool_text for word in ["$1000", "$5000", "$10000", "1000", "5000", "10000"]):
        prize_value_score = 12

    years_exp = _years_experience(profile)
    skill_level_match = 20
    if "beginner" in hack_tokens and years_exp < 2:
        skill_level_match = 25
    elif "advanced" in hack_tokens and years_exp >= 5:
        skill_level_match = 25
    elif "intermediate" in hack_tokens and 2 <= years_exp < 5:
        skill_level_match = 25

    location_match = 15
    if "virtual" in hackathon.get("remote_type", "").lower() or "virtual" in prize_pool_text:
        location_match = 15
    elif "in-person" in prize_pool_text or "onsite" in prize_pool_text:
        location_match = 10

    team_collab = 5

    raw_score = tech_stack_match + prize_value_score + skill_level_match + location_match + team_collab
    score = max(0, min(100, int(raw_score)))
    priority = "High" if score >= 75 else "Medium" if score >= 55 else "Low" if score >= 35 else "Skip"

    return {
        "match_score": score,
        "priority": priority,
        "tech_alignment_score": tech_stack_match,
        "prize_value_score": prize_value_score,
        "skill_level_match": skill_level_match,
        "location_match": location_match,
        "team_collaboration_fit": team_collab,
        "good_fit": f"Tech skills overlap: {', '.join(sorted(list(skill_overlap))[:10])}. Prize and format alignment strong." if skill_overlap else "Format aligns with learning goals.",
        "weak_areas": "Verify team formation requirements and time commitment needed.",
        "red_flags": "No obvious red flags." if score >= 35 else "Low skill/prize alignment with this hackathon.",
        "opportunity_type": "hackathon",
    }


def _score_competition(profile: Dict[str, Any], competition: Dict[str, Any]) -> Dict[str, Any]:
    """Score competition opportunities based on win potential and prestige"""
    cv_skills = _tokens(" ".join(str(profile.get(k, "")) for k in ["cv_text", "skills", "target_roles"]))
    comp_tokens = _tokens(" ".join(str(competition.get(k, "")) for k in ["title", "company", "description"]))
    skill_overlap = cv_skills & comp_tokens

    years_exp = _years_experience(profile)
    skill_ceiling_score = 20 + (min(20, years_exp * 2))

    prestige_words = ["renowned", "prestigious", "major", "international", "global", "championship"]
    prestige_score = 25 if any(w in comp_tokens for w in prestige_words) else 15

    comp_text = str(competition.get("description", "")).lower()
    difficulty_map = {"beginner": 10, "intermediate": 15, "advanced": 20, "expert": 5}
    competitive_difficulty = next((v for k, v in difficulty_map.items() if k in comp_text), 15)

    deadline = competition.get("deadline", "")
    time_availability = 15 if deadline else 10

    category_match = 10 if skill_overlap else 5

    raw_score = skill_ceiling_score + prestige_score + competitive_difficulty + time_availability + category_match
    score = max(0, min(100, int(raw_score)))
    priority = "High" if score >= 75 else "Medium" if score >= 55 else "Low" if score >= 35 else "Skip"

    return {
        "match_score": score,
        "priority": priority,
        "skill_ceiling_score": skill_ceiling_score,
        "prestige_score": prestige_score,
        "competitive_difficulty": competitive_difficulty,
        "time_availability": time_availability,
        "category_relevance": category_match,
        "good_fit": f"Strong prestige and skill alignment with focus on: {', '.join(sorted(list(skill_overlap))[:5])}." if skill_overlap else "Competition format aligns with profile.",
        "weak_areas": "Check past winners' profiles to assess competitiveness.",
        "red_flags": "No red flags detected." if score >= 35 else "Significant skill gap vs. competition level.",
        "opportunity_type": "competition",
    }


def _score_webinar(profile: Dict[str, Any], webinar: Dict[str, Any]) -> Dict[str, Any]:
    """Score webinar opportunities based on learning relevance and time fit"""
    cv_text = str(profile.get("cv_text", "") + " " + profile.get("industries", "") + " " + profile.get("target_roles", "")).lower()
    webinar_text = str(webinar.get("title", "") + " " + webinar.get("description", "") + " " + webinar.get("raw_text", "")).lower()

    topic_keywords = _tokens(webinar_text)
    profile_keywords = _tokens(cv_text)
    topic_overlap = topic_keywords & profile_keywords
    topic_relevance = min(35, len(topic_overlap) * 5)

    speaker_reputation = 15
    if "professor" in webinar_text or "phd" in webinar_text or "expert" in webinar_text:
        speaker_reputation = 20

    skill_level_words = {"beginner": 25, "intermediate": 20, "advanced": 25, "introductory": 25}
    years_exp = _years_experience(profile)
    skill_level_match = 20
    for level, points in skill_level_words.items():
        if level in webinar_text:
            if (level == "beginner" and years_exp < 2) or (level == "intermediate" and 2 <= years_exp < 5) or (level == "advanced" and years_exp >= 5):
                skill_level_match = points
            break

    time_investment = 15
    if "30 minutes" in webinar_text or "1 hour" in webinar_text:
        time_investment = 15
    elif "2 hours" in webinar_text or "3 hours" in webinar_text:
        time_investment = 10

    cert_value = 5 if "certification" in webinar_text or "certificate" in webinar_text else 0

    raw_score = topic_relevance + speaker_reputation + skill_level_match + time_investment + cert_value
    score = max(0, min(100, int(raw_score)))
    priority = "High" if score >= 75 else "Medium" if score >= 55 else "Low" if score >= 35 else "Skip"

    return {
        "match_score": score,
        "priority": priority,
        "topic_relevance": topic_relevance,
        "speaker_reputation": speaker_reputation,
        "skill_level_match": skill_level_match,
        "time_investment_score": time_investment,
        "certification_value": cert_value,
        "good_fit": f"Strong topic relevance: {', '.join(sorted(list(topic_overlap))[:8])}. Learning objectives align with career goals." if topic_overlap else "Format fits your learning style.",
        "weak_areas": "Verify speaker credentials and learning outcomes.",
        "red_flags": "No red flags detected." if score >= 35 else "Topic misalignment with current learning goals.",
        "opportunity_type": "webinar",
    }


def score_opportunity(profile: Dict[str, Any], opportunity: Dict[str, Any], opp_type: str = "job") -> Dict[str, Any]:
    """Route to appropriate scoring function based on opportunity type"""
    if opp_type == "hackathon":
        fallback = _score_hackathon(profile, opportunity)
    elif opp_type == "competition":
        fallback = _score_competition(profile, opportunity)
    elif opp_type == "webinar":
        fallback = _score_webinar(profile, opportunity)
    else:
        fallback = _score_job_opportunity(profile, opportunity)

    system = f"You are a careful {opp_type}-fit evaluator. Return only JSON. Do not discriminate or infer protected characteristics."
    if opp_type == "job":
        system += " Respect user deal-breakers."

    prompt_map = {
        "job": "Score this job from 0-100 for the user. Use these components: skill_match, title_match, seniority_match, location_match, salary_match, industry_match, authorization_match, deal_breaker_penalty.",
        "hackathon": "Score this hackathon from 0-100 for the user. Use these components: tech_alignment_score, prize_value_score, skill_level_match, location_match, team_collaboration_fit.",
        "competition": "Score this competition from 0-100 for the user. Use these components: skill_ceiling_score, prestige_score, competitive_difficulty, time_availability, category_relevance.",
        "webinar": "Score this webinar from 0-100 for the user. Use these components: topic_relevance, speaker_reputation, skill_level_match, time_investment_score, certification_value.",
    }

    user = f"""
{prompt_map.get(opp_type, prompt_map['job'])}
Return JSON with: match_score, priority High/Medium/Low/Skip, component scores, good_fit, weak_areas, red_flags.

USER PROFILE:\n{profile}

OPPORTUNITY:\n{opportunity}
"""
    data = ask_json(system, user, fallback)
    for k, v in fallback.items():
        data.setdefault(k, v)
    return data


def score_job(profile: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    """Backward compatible wrapper - score a job"""
    return score_opportunity(profile, job, opp_type=job.get("opportunity_type") or "job")
