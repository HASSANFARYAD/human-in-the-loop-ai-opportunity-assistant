from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from job_assistant.auth import current_user
from job_assistant.db import (
    get_integration_settings,
    list_recordings,
    save_recording,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class RecordingIn(BaseModel):
    job_id: Optional[int] = None
    title: str = "Interview practice recording"
    mime_type: str = "audio/webm"
    data_url: str
    duration_ms: int = 0


def _recording_storage_config(user_id: int) -> dict:
    settings = get_integration_settings(user_id, "recording_storage")
    config = settings.get("config") or {}
    if settings and config.get("is_active") is False:
        raise HTTPException(status_code=400, detail="Recording storage configuration is inactive.")
    storage_type = str(config.get("storage_type") or "local").strip().lower()
    if storage_type != "local":
        raise HTTPException(status_code=400, detail=f"Recording storage type '{storage_type}' is not supported by this deployment.")
    storage_path = str(config.get("storage_path") or "data/recordings").strip()
    allowed = config.get("allowed_mime_types") or ["audio/webm", "audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg"]
    if isinstance(allowed, str):
        allowed = [item.strip() for item in allowed.replace(",", " ").split() if item.strip()]
    return {
        "storage_type": storage_type,
        "storage_path": storage_path,
        "max_upload_size": int(config.get("max_upload_size") or 25 * 1024 * 1024),
        "allowed_mime_types": allowed,
    }


def _safe_audio_extension(filename: str, mime_type: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4"}:
        return suffix
    return {
        "audio/webm": ".webm",
        "audio/wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
    }.get(mime_type, ".webm")


@router.post("/recordings")
async def post_recording(payload: RecordingIn, user: dict = Depends(current_user)):
    if not payload.data_url.startswith("data:audio/"):
        raise HTTPException(status_code=400, detail="Recording payload must be an audio data URL")
    recording = payload.dict()
    recording["storage_type"] = "legacy_data_url"
    recording["playback_url"] = payload.data_url
    return save_recording(user["id"], recording, job_id=payload.job_id)


@router.post("/recordings/upload")
async def upload_recording(
    job_id: Optional[int] = Form(default=None),
    title: str = Form(default="Interview practice recording"),
    duration_ms: int = Form(default=0),
    interview_prep_session_id: Optional[int] = Form(default=None),
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    config = _recording_storage_config(user["id"])
    mime_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if mime_type not in set(config["allowed_mime_types"]):
        raise HTTPException(status_code=400, detail=f"Recording type '{mime_type}' is not allowed.")
    content = await file.read()
    if len(content) > int(config["max_upload_size"]):
        raise HTTPException(status_code=413, detail="Recording exceeds the configured maximum upload size.")
    base_dir = Path(config["storage_path"]).expanduser().resolve()
    user_dir = (base_dir / str(user["id"])).resolve()
    if not str(user_dir).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid recording storage path.")
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(file.filename or "recording").stem).strip("-")[:80] or "recording"
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(8)}-{safe_title}{_safe_audio_extension(file.filename or '', mime_type)}"
    stored_path = (user_dir / stored_name).resolve()
    if not str(stored_path).startswith(str(user_dir)):
        raise HTTPException(status_code=400, detail="Invalid recording filename.")
    stored_path.write_bytes(content)
    playback_url = f"/api/v1/recordings/{stored_name}/file"
    recording = {
        "title": title,
        "mime_type": mime_type,
        "data_url": "",
        "duration_ms": duration_ms,
        "interview_prep_session_id": interview_prep_session_id,
        "original_filename": file.filename or "",
        "stored_path": str(stored_path),
        "playback_url": playback_url,
        "file_size": len(content),
        "storage_type": config["storage_type"],
    }
    return save_recording(user["id"], recording, job_id=job_id)


@router.get("/recordings")
async def get_recordings(job_id: Optional[int] = None, user: dict = Depends(current_user)):
    return list_recordings(user["id"], job_id=job_id)


@router.get("/recordings/{filename}/file")
async def get_recording_file(filename: str, user: dict = Depends(current_user)):
    rows = list_recordings(user["id"], limit=500)
    for row in rows:
        stored_path = row.get("stored_path") or ""
        if stored_path and Path(stored_path).name == filename:
            path = Path(stored_path)
            if not path.exists():
                raise HTTPException(status_code=404, detail="Recording file not found")
            return FileResponse(path, media_type=row.get("mime_type") or "audio/webm", filename=row.get("original_filename") or filename)
    raise HTTPException(status_code=404, detail="Recording not found")
