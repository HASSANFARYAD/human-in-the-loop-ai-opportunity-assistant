from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from urllib.parse import urlencode

from job_assistant.auth import current_user
from job_assistant.config import settings
from job_assistant.db import get_integration_settings, list_gmail_messages, save_gmail_messages
from job_assistant.services.gmail_ingest import build_gmail_authorization_url, disconnect_gmail, exchange_gmail_code, get_gmail_connection

logger = logging.getLogger(__name__)

router = APIRouter()


class GmailMessagesIn(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)


def _frontend_redirect(path: str, params: dict[str, str]) -> str:
    base_url = settings.frontend_base_url.rstrip("/")
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("Invalid FRONTEND_BASE_URL configured for OAuth redirect: %s", settings.frontend_base_url)
        base_url = "http://localhost:3000"
    safe_path = path if path.startswith("/") and not path.startswith("//") else "/"
    return f"{base_url}{safe_path}?{urlencode(params)}"


@router.get("/gmail/status")
async def get_gmail_status(user: dict = Depends(current_user)):
    connection = get_gmail_connection(user["id"])
    return {**connection, "status": "connected" if connection.get("connected") else ("configured" if connection.get("configured") else "not_configured")}


@router.get("/gmail/auth-url")
async def get_gmail_auth_url(user: dict = Depends(current_user)):
    try:
        return {"url": build_gmail_authorization_url(user["id"])}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/gmail/oauth/callback")
async def gmail_oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "error", "message": error}))
    if not code or not state:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "error", "message": "missing_oauth_callback_values"}))
    try:
        parts = state.split(":")
        if len(parts) < 3 or parts[0] != "gmail":
            raise RuntimeError("Invalid Gmail OAuth state.")
        user_id = int(parts[1])
        settings = get_integration_settings(user_id, "gmail")
        redirect_uri = (settings.get("config") or {}).get("redirect_uri")
        exchange_gmail_code(user_id, code, redirect_uri, state)
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "connected"}))
    except Exception as exc:
        return RedirectResponse(_frontend_redirect("/integrations", {"service": "gmail", "gmail": "error", "message": str(exc)}))


@router.post("/gmail/disconnect")
async def post_gmail_disconnect(user: dict = Depends(current_user)):
    disconnect_gmail(user["id"])
    return {"status": "success", "connected": False}


@router.get("/gmail/messages")
async def get_gmail_messages(limit: int = 50, user: dict = Depends(current_user)):
    return list_gmail_messages(user["id"], limit=limit)


@router.post("/gmail/messages")
async def post_gmail_messages(payload: GmailMessagesIn, user: dict = Depends(current_user)):
    return {"status": "success", "messages": save_gmail_messages(user["id"], payload.messages)}
