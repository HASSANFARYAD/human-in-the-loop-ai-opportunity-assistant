from __future__ import annotations

from typing import Any, Dict

import requests


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
