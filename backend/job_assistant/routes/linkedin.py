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
