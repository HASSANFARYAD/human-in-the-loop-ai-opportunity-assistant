from __future__ import annotations

import json
import os
from typing import Any, Dict


def has_openai() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _extract_text(response: Any) -> str:
    if hasattr(response, "output_text"):
        return response.output_text
    try:
        return response.output[0].content[0].text
    except Exception:
        return str(response)


def ask_json(system: str, user: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not has_openai():
        return fallback
    try:
        from openai import OpenAI

        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-5.5")
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = _extract_text(response).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end >= start:
            return json.loads(text[start : end + 1])
        return fallback
    except Exception as exc:
        out = dict(fallback)
        out["_ai_error"] = str(exc)
        return out
