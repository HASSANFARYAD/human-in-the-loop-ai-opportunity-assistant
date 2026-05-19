from __future__ import annotations

import base64
import os
from email.utils import parsedate_to_datetime
from typing import Dict, List

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_service():
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
                raise FileNotFoundError(f"Missing {credentials_file}. Create OAuth Desktop credentials in Google Cloud Console.")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


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


def fetch_job_alert_messages(query: str = '("job alert" OR "new jobs" OR recruiter OR "is hiring") newer_than:30d', max_results: int = 20) -> List[Dict]:
    service = _get_service()
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
