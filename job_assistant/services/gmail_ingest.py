from __future__ import annotations

import base64
import json
import os
import secrets
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Tuple

from job_assistant.db import delete_integration_settings, get_integration_settings, save_integration_settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_SERVICE_NAME = "gmail_oauth"
GMAIL_OAUTH_STATE_SERVICE_NAME = "gmail_oauth_state"


def _client_config() -> dict:
    """Load Google OAuth client config from env vars or a credentials.json file.

    For multi-user SaaS, use a Google OAuth Web client. Desktop credentials and
    token.json are supported only as a backwards-compatible local dev fallback.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    project_id = os.getenv("GOOGLE_PROJECT_ID", "job-assistant")
    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "project_id": project_id,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            }
        }

    credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    path = Path(credentials_file)
    if not path.exists():
        raise FileNotFoundError(
            "Missing Google OAuth configuration. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, "
            "or provide GOOGLE_CREDENTIALS_FILE=credentials.json."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _flow(redirect_uri: str):
    from google_auth_oauthlib.flow import Flow

    config = _client_config()
    flow = Flow.from_client_config(
        config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        autogenerate_code_verifier=False,
    )
    return flow


def build_gmail_authorization_url(user_id: int, redirect_uri: str) -> str:
    """Return a Google consent URL for the current app user.

    The state includes the local user id plus a one-time nonce. Tokens are not
    put in the URL; they are exchanged server-side and stored encrypted in
    integration_settings.
    """
    oauth_nonce = secrets.token_urlsafe(32)
    oauth_state = f"gmail:{user_id}:{oauth_nonce}"
    save_integration_settings(
        user_id,
        GMAIL_OAUTH_STATE_SERVICE_NAME,
        api_key="",
        config={"state": oauth_state},
    )

    flow = _flow(redirect_uri)
    authorization_url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=oauth_state,
    )
    return authorization_url


def exchange_gmail_code(user_id: int, code: str, redirect_uri: str, state: str) -> None:
    """Exchange an OAuth callback code and save this user's encrypted credentials."""
    state_settings = get_integration_settings(user_id, GMAIL_OAUTH_STATE_SERVICE_NAME)
    expected_state = state_settings.get("config", {}).get("state") if state_settings else ""
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise RuntimeError("Invalid or expired Gmail OAuth state. Please start the Gmail connection again.")

    flow = _flow(redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    save_integration_settings(
        user_id,
        GMAIL_SERVICE_NAME,
        api_key="",
        config={
            "credentials_json": creds.to_json(),
            "scopes": SCOPES,
            "connected_email": _gmail_profile_email(creds),
        },
    )
    delete_integration_settings(user_id, GMAIL_OAUTH_STATE_SERVICE_NAME)


def disconnect_gmail(user_id: int) -> None:
    delete_integration_settings(user_id, GMAIL_SERVICE_NAME)


def get_gmail_connection(user_id: int) -> dict:
    settings = get_integration_settings(user_id, GMAIL_SERVICE_NAME)
    config = settings.get("config", {}) if settings else {}
    if not config.get("credentials_json"):
        return {"connected": False}
    return {
        "connected": True,
        "connected_email": config.get("connected_email", ""),
        "scopes": config.get("scopes", SCOPES),
    }


def _credentials_for_user(user_id: int):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    settings = get_integration_settings(user_id, GMAIL_SERVICE_NAME)
    config = settings.get("config", {}) if settings else {}
    credentials_json = config.get("credentials_json")
    if not credentials_json:
        raise RuntimeError("Gmail is not connected for this user. Connect Gmail from Ingest Opportunities > Gmail read-only.")

    creds = Credentials.from_authorized_user_info(json.loads(credentials_json), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config["credentials_json"] = creds.to_json()
        save_integration_settings(user_id, GMAIL_SERVICE_NAME, api_key="", config=config)
    if not creds.valid:
        raise RuntimeError("Gmail authorization expired or is invalid. Please reconnect Gmail.")
    return creds


def _legacy_local_service():
    """Single-user local fallback retained for development only."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(f"Missing {credentials_file}. Create OAuth credentials in Google Cloud Console.")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _get_service(user_id: int | None = None):
    from googleapiclient.discovery import build

    if user_id is None:
        return _legacy_local_service()
    return build("gmail", "v1", credentials=_credentials_for_user(user_id))


def _gmail_profile_email(creds) -> str:
    try:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")
    except Exception:
        return ""


def _decode_part(part: Dict) -> str:
    body = part.get("body", {})
    data = body.get("data")
    if data:
        return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="ignore")
    return ""


def _extract_body(payload: Dict) -> str:
    if payload.get("parts"):
        text = []
        for part in payload["parts"]:
            if part.get("mimeType") in {"text/plain", "text/html"}:
                text.append(_decode_part(part))
            elif part.get("parts"):
                text.append(_extract_body(part))
        return "\n".join(text)
    return _decode_part(payload)


def fetch_job_alert_messages(
    user_id: int | None = None,
    query: str = '("job alert" OR "new jobs" OR recruiter OR "is hiring") newer_than:30d',
    max_results: int = 20,
) -> List[Dict]:
    service = _get_service(user_id)
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = result.get("messages", [])
    out = []
    for msg in messages:
        full = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        payload = full.get("payload", {})
        headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}
        date_received = ""
        if headers.get("date"):
            try:
                date_received = parsedate_to_datetime(headers["date"]).date().isoformat()
            except Exception:
                date_received = headers["date"]
        out.append({
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "date_received": date_received,
            "body": _extract_body(payload),
        })
    return out
