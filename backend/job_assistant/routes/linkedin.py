from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from urllib.parse import urlencode

from job_assistant.auth import current_user
from job_assistant.config import settings
from job_assistant.db import get_integration_settings
from job_assistant.services.linkedin_integration import (
    build_linkedin_authorization_url,
    disconnect_linkedin,
    exchange_linkedin_code,
    get_linkedin_connection,
    search_linkedin_jobs_official,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class LinkedinSearchIn(BaseModel):
    title_filter: str = Field(min_length=1)
    location_filter: str = ""
    offset: int = 0
    count: int = 10
    workspace_id: int | None = None


def _frontend_redirect(path: str, params: dict[str, str]) -> str:
    base_url = settings.frontend_base_url.rstrip("/")
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("Invalid FRONTEND_BASE_URL configured for OAuth redirect: %s", settings.frontend_base_url)
        base_url = "http://localhost:3000"
    safe_path = path if path.startswith("/") and not path.startswith("//") else "/"
    return f"{base_url}{safe_path}?{urlencode(params)}"


@router.get("/linkedin/status")
async def get_linkedin_status(user: dict = Depends(current_user)):
    connection = get_linkedin_connection(user["id"])
    return {**connection, "status": "connected" if connection.get("connected") else ("configured" if connection.get("configured") else "not_configured")}


@router.get("/linkedin/auth-url")
async def get_linkedin_auth_url(user: dict = Depends(current_user)):
    try:
        return {"url": build_linkedin_authorization_url(user["id"])}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/linkedin/oauth/callback")
async def linkedin_oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "linkedin", "linkedin": "error", "message": error}))
    if not code or not state:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "linkedin", "linkedin": "error", "message": "missing_oauth_callback_values"}))
    try:
        parts = state.split(":")
        if len(parts) < 3 or parts[0] != "linkedin":
            raise RuntimeError("Invalid LinkedIn OAuth state.")
        user_id = int(parts[1])
        linkedin_settings = get_integration_settings(user_id, "linkedin")
        redirect_uri = (linkedin_settings.get("config") or {}).get("redirect_uri")
        exchange_linkedin_code(user_id, code, redirect_uri, state)
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "linkedin", "linkedin": "connected"}))
    except Exception as exc:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "linkedin", "linkedin": "error", "message": str(exc)}))


@router.post("/linkedin/disconnect")
async def post_linkedin_disconnect(user: dict = Depends(current_user)):
    disconnect_linkedin(user["id"])
    return {"status": "success", "connected": False}


@router.post("/linkedin/jobs/search")
async def linkedin_jobs_search(payload: LinkedinSearchIn, user: dict = Depends(current_user)):
    from job_assistant.services.linkedin_integration import _credentials_for_user

    try:
        creds = _credentials_for_user(user["id"])
        access_token = creds.get("access_token", "")
        if not access_token:
            raise HTTPException(status_code=400, detail="LinkedIn is not connected. Connect LinkedIn in Integrations first.")
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        items = search_linkedin_jobs_official(
            access_token,
            payload.title_filter,
            payload.location_filter,
            payload.offset,
            payload.count,
        )
        return {"status": "success", "opportunities": items, "raw_count": len(items)}
    except Exception as exc:
        logger.error(f"Error searching official LinkedIn Jobs API: {exc}")
        raise HTTPException(status_code=502, detail=f"LinkedIn Jobs API search failed: {exc}")


class LinkedinEasyApplyIn(BaseModel):
    job_url: str = Field(min_length=1, description="Full LinkedIn job URL to apply to")
    dry_run: bool = True
    workspace_id: int | None = None


class LinkedinBulkEasyApplyIn(BaseModel):
    job_ids: list[int] = Field(min_length=1, max_length=10)
    dry_run: bool = True
    workspace_id: int | None = None


class LinkedinSessionCookiesIn(BaseModel):
    li_at: str = Field(min_length=1, description="LinkedIn session cookie 'li_at' value")
    jsessionid: str = Field(default="", description="LinkedIn JSESSIONID cookie value")


@router.get("/linkedin/cookies-status")
async def get_linkedin_cookies_status(user: dict = Depends(current_user)):
    settings = get_integration_settings(user["id"], "linkedin_browser")
    config = settings.get("config", {}) if settings else {}
    has_cookies = bool(config.get("li_at"))
    return {"has_cookies": has_cookies}


@router.post("/linkedin/cookies")
async def save_linkedin_cookies(payload: LinkedinSessionCookiesIn, user: dict = Depends(current_user)):
    from job_assistant.db import save_integration_settings

    save_integration_settings(
        user["id"],
        "linkedin_browser",
        api_key="",
        config={
            "li_at": payload.li_at,
            "jsessionid": payload.jsessionid,
        },
    )
    return {"status": "success", "has_cookies": True}


@router.post("/linkedin/easy-apply")
async def linkedin_easy_apply(payload: LinkedinEasyApplyIn, user: dict = Depends(current_user)):
    from job_assistant.services.linkedin_easy_apply import easy_apply_for_job
    from job_assistant.services.linkedin_integration import get_linkedin_connection

    browser_settings = get_integration_settings(user["id"], "linkedin_browser")
    config = browser_settings.get("config", {}) if browser_settings else {}
    li_at = config.get("li_at", "")
    jsessionid = config.get("jsessionid", "")

    if not li_at:
        raise HTTPException(status_code=400, detail="LinkedIn browser cookies not saved. Save session cookies in Integrations first.")

    profile = get_linkedin_connection(user["id"])
    application_data = {}
    if profile.get("connected"):
        application_data["email"] = profile.get("connected_email", "")
        application_data["linkedin_url"] = f"https://linkedin.com/in/{profile.get('connected_name', '').replace(' ', '-')}"

    result = await easy_apply_for_job(
        user["id"],
        payload.job_url,
        li_at=li_at,
        jsessionid=jsessionid,
        application_data=application_data,
        dry_run=payload.dry_run,
    )
    return {"status": result.get("status"), "result": result}


@router.post("/linkedin/bulk-easy-apply")
async def linkedin_bulk_easy_apply(payload: LinkedinBulkEasyApplyIn, user: dict = Depends(current_user)):
    from job_assistant.db.jobs import get_job
    from job_assistant.services.linkedin_easy_apply import easy_apply_for_job

    browser_settings = get_integration_settings(user["id"], "linkedin_browser")
    config = browser_settings.get("config", {}) if browser_settings else {}
    li_at = config.get("li_at", "")
    jsessionid = config.get("jsessionid", "")

    if not li_at:
        raise HTTPException(status_code=400, detail="LinkedIn browser cookies not saved. Save session cookies in Integrations first.")

    results: list[dict] = []
    for jid in payload.job_ids:
        job = get_job(user["id"], jid, workspace_id=payload.workspace_id)
        if not job:
            results.append({"job_id": jid, "status": "skipped", "reason": "Job not found"})
            continue
        url = str(job.get("url") or "")
        if "linkedin.com" not in url.lower():
            results.append({"job_id": jid, "status": "skipped", "reason": "Not a LinkedIn job URL", "url": url})
            continue
        result = await easy_apply_for_job(
            user["id"],
            url,
            li_at=li_at,
            jsessionid=jsessionid,
            dry_run=payload.dry_run,
        )
        results.append({"job_id": jid, **result})

    return {"status": "completed", "results": results, "dry_run": payload.dry_run}
