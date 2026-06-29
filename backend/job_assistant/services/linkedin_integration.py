from __future__ import annotations

import json
import secrets
from typing import Any, Dict
from urllib.parse import urlencode

import requests

from job_assistant.db import delete_integration_settings, get_integration_settings, save_integration_settings

# ── Constants ──────────────────────────────────────────────────────────────

LINKEDIN_OAUTH_SERVICE = "linkedin_oauth"
LINKEDIN_OAUTH_STATE_SERVICE = "linkedin_oauth_state"
LINKEDIN_CONFIG_SERVICE = "linkedin"

LINKEDIN_SCOPES = [
    "openid",
    "profile",
    "email",
    "w_member_social",
]

LINKEDIN_AUTH_URI = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URI = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_API_BASE = "https://api.linkedin.com/rest"

# ── OAuth2 helpers ─────────────────────────────────────────────────────────

def _oauth_settings(user_id: int) -> dict:
    settings = get_integration_settings(user_id, LINKEDIN_CONFIG_SERVICE)
    config = settings.get("config") or {}
    if config.get("is_active") is False:
        raise RuntimeError("LinkedIn OAuth configuration is inactive.")
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(settings.get("api_key") or config.get("client_secret") or "").strip()
    redirect_uri = str(config.get("redirect_uri") or "").strip()
    scopes = config.get("scopes") or LINKEDIN_SCOPES
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.replace(",", " ").split() if s.strip()]
    if not client_id or not client_secret or not redirect_uri:
        raise RuntimeError("LinkedIn OAuth is missing database configuration for client_id, client_secret, or redirect_uri.")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scopes": scopes or LINKEDIN_SCOPES,
    }


def build_linkedin_authorization_url(user_id: int, redirect_uri: str | None = None) -> str:
    oauth_nonce = secrets.token_urlsafe(32)
    oauth_state = f"linkedin:{user_id}:{oauth_nonce}"
    save_integration_settings(
        user_id,
        LINKEDIN_OAUTH_STATE_SERVICE,
        api_key="",
        config={"state": oauth_state},
    )

    oauth = _oauth_settings(user_id)
    params = {
        "response_type": "code",
        "client_id": oauth["client_id"],
        "redirect_uri": redirect_uri or oauth["redirect_uri"],
        "state": oauth_state,
        "scope": " ".join(oauth["scopes"]),
    }
    return f"{LINKEDIN_AUTH_URI}?{urlencode(params)}"


def exchange_linkedin_code(user_id: int, code: str, redirect_uri: str | None, state: str) -> None:
    state_settings = get_integration_settings(user_id, LINKEDIN_OAUTH_STATE_SERVICE)
    expected_state = state_settings.get("config", {}).get("state") if state_settings else ""
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise RuntimeError("Invalid or expired LinkedIn OAuth state. Please start the LinkedIn connection again.")

    oauth = _oauth_settings(user_id)
    token_response = requests.post(
        LINKEDIN_TOKEN_URI,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or oauth["redirect_uri"],
            "client_id": oauth["client_id"],
            "client_secret": oauth["client_secret"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if token_response.status_code != 200:
        raise RuntimeError(f"LinkedIn token exchange failed: {token_response.status_code} {token_response.text[:500]}")

    token_data = token_response.json()
    credentials = {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_in": token_data.get("expires_in", 0),
        "token_type": token_data.get("token_type", "Bearer"),
    }

    profile_info = _linkedin_profile_info(token_data["access_token"])

    save_integration_settings(
        user_id,
        LINKEDIN_OAUTH_SERVICE,
        api_key="",
        config={
            "credentials_json": json.dumps(credentials),
            "scopes": oauth["scopes"],
            "connected_name": profile_info.get("name", ""),
            "connected_email": profile_info.get("email", ""),
            "connected_sub": profile_info.get("sub", ""),
            "author_urn": profile_info.get("author_urn", ""),
        },
    )
    delete_integration_settings(user_id, LINKEDIN_OAUTH_STATE_SERVICE)


def disconnect_linkedin(user_id: int) -> None:
    delete_integration_settings(user_id, LINKEDIN_OAUTH_SERVICE)


def get_linkedin_connection(user_id: int) -> dict:
    settings = get_integration_settings(user_id, LINKEDIN_OAUTH_SERVICE)
    config = settings.get("config", {}) if settings else {}
    oauth_config = get_integration_settings(user_id, LINKEDIN_CONFIG_SERVICE)
    configured = bool(oauth_config) and (oauth_config.get("config") or {}).get("is_active") is not False
    if not config.get("credentials_json"):
        return {"connected": False, "configured": configured}
    return {
        "connected": True,
        "configured": configured,
        "connected_name": config.get("connected_name", ""),
        "connected_email": config.get("connected_email", ""),
        "author_urn": config.get("author_urn", ""),
        "scopes": config.get("scopes", LINKEDIN_SCOPES),
    }


def _credentials_for_user(user_id: int) -> dict:
    settings = get_integration_settings(user_id, LINKEDIN_OAUTH_SERVICE)
    config = settings.get("config", {}) if settings else {}
    credentials_json = config.get("credentials_json")
    if not credentials_json:
        raise RuntimeError("LinkedIn is not connected for this user. Connect LinkedIn from Integrations.")

    credentials = json.loads(credentials_json) if isinstance(credentials_json, str) else credentials_json
    access_token = credentials.get("access_token", "")
    if not access_token:
        raise RuntimeError("LinkedIN access token is missing. Please reconnect LinkedIn.")
    return credentials


def _linkedin_profile_info(access_token: str) -> dict:
    try:
        resp = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            sub = data.get("sub", "")
            name = data.get("name", "") or f"{data.get('given_name', '')} {data.get('family_name', '')}".strip()
            email = data.get("email", "")
            author_urn = f"urn:li:person:{sub}" if sub else ""
            return {"name": name, "email": email, "sub": sub, "author_urn": author_urn}
    except Exception:
        pass
    return {"name": "", "email": "", "sub": "", "author_urn": ""}


# ── Official LinkedIn Jobs Search ──────────────────────────────────────────

OFFICIAL_JOBS_SEARCH_ENDPOINT = "https://api.linkedin.com/rest/jobs/search"


def search_linkedin_jobs_official(
    access_token: str,
    title_filter: str,
    location_filter: str,
    offset: int = 0,
    count: int = 10,
) -> list[dict[str, Any]]:
    if not access_token.strip():
        raise ValueError("Missing LinkedIn access token.")
    if not title_filter.strip():
        raise ValueError("Title/search filter is required.")

    response = requests.post(
        OFFICIAL_JOBS_SEARCH_ENDPOINT,
        headers={
            "Authorization": f"Bearer {access_token.strip()}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202604",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json={
            "keyword": title_filter.strip(),
            "location": location_filter.strip() or "Remote",
            "start": max(0, offset),
            "count": max(1, min(count, 50)),
        },
        timeout=30,
    )
    if response.status_code == 403:
        raise RuntimeError(
            "LinkedIn Jobs API requires a Recruiter or Talent Hub license. "
            "Use RapidAPI LinkedIn as an alternative for job search."
        )
    if response.status_code != 200:
        raise RuntimeError(f"LinkedIn Jobs API search failed: {response.status_code} {response.text[:500]}")

    data = response.json()
    elements = data.get("elements", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    return [_normalize_official_job(item) for item in elements if isinstance(item, dict)]


def _normalize_official_job(item: dict) -> dict:
    title = _first(item, ["title", "jobTitle", "name"])
    company_data = item.get("companyDetails", {}) or item.get("company", {})
    company = company_data.get("name") if isinstance(company_data, dict) else str(company_data) if company_data else ""
    location_data = item.get("location", {}) or item.get("formattedLocation", {})
    location = location_data if isinstance(location_data, str) else (location_data.get("name") if isinstance(location_data, dict) else "")

    return {
        "title": title or "Untitled LinkedIn Job",
        "company": company,
        "location": location,
        "remote_type": _infer_remote_type(item),
        "url": item.get("listingUrl", "") or item.get("url", "") or "",
        "source": "LinkedIn Official API",
        "date_received": "",
        "description": item.get("description", {}).get("text", "") if isinstance(item.get("description"), dict) else str(item.get("description", "")),
        "salary_min": "",
        "salary_max": "",
        "deadline": "",
        "opportunity_type": "job",
        "raw_text": json.dumps(item, ensure_ascii=False),
    }


# ── Publishing ─────────────────────────────────────────────────────────────

def publish_text_post(api_token: str, author_urn: str, text: str, linkedin_version: str = "202604") -> Dict[str, Any]:
    if not api_token.strip():
        raise ValueError("Missing LinkedIn access token.")
    if not author_urn.strip().startswith("urn:li:"):
        raise ValueError("Author URN must look like urn:li:person:... or urn:li:organization:...")
    if not text.strip():
        raise ValueError("Post text is required.")

    payload = {
        "author": author_urn.strip(),
        "commentary": text.strip(),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    response = requests.post(
        "https://api.linkedin.com/rest/posts",
        headers={
            "Authorization": f"Bearer {api_token.strip()}",
            "Content-Type": "application/json",
            "LinkedIn-Version": linkedin_version.strip() or "202604",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json=payload,
        timeout=30,
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"LinkedIn publish failed: {response.status_code} {response.text[:500]}")
    return {
        "status_code": response.status_code,
        "post_id": response.headers.get("x-restli-id", ""),
    }


# ── Shared helpers ─────────────────────────────────────────────────────────

def _first(item: Dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        text = str(value).strip()
        if text:
            return text
    return ""


def _infer_remote_type(item: Dict[str, Any]) -> str:
    text = json.dumps(item, ensure_ascii=False).lower()
    if "remote" in text or "work from home" in text or "wfh" in text:
        return "Remote"
    if "hybrid" in text:
        return "Hybrid"
    return ""
