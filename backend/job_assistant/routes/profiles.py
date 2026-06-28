from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from job_assistant.auth import current_user
from job_assistant.db import (
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    set_default_profile,
    update_profile_fields,
    upsert_profile,
)
from job_assistant.services.parsing import extract_profile_from_resume, extract_text_from_upload

logger = logging.getLogger(__name__)

router = APIRouter()


class ProfileCreate(BaseModel):
    name: str = ""
    cv_text: str = ""
    target_roles: str = ""
    industries: str = ""
    locations: str = ""
    remote_preference: str = ""
    salary_expectations: str = ""
    work_authorization: str = ""
    years_experience: str = ""
    skills: str = ""
    deal_breakers: str = ""
    full_name: str = ""
    email: str = ""
    preferred_role: str = ""
    country: str = ""
    job_preferences: str = ""
    platforms: str = ""
    resume_name: str = ""
    integration_status: str = ""


_RESUME_DERIVED_FIELDS = (
    "cv_text",
    "target_roles",
    "industries",
    "locations",
    "remote_preference",
    "work_authorization",
    "years_experience",
    "skills",
)

_MAX_RESUME_BYTES = 5 * 1024 * 1024


@router.get("/profile")
async def get_user_profile(user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"])
        return profile or {}
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get profile")


@router.post("/profile")
async def update_profile(profile_data: ProfileCreate, user: dict = Depends(current_user)):
    try:
        upsert_profile(profile_data.dict(), user["id"])
        return {"status": "success", "message": "Profile updated"}
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")


@router.get("/profiles")
async def list_user_profiles(user: dict = Depends(current_user)):
    return list_profiles(user["id"])


@router.post("/profiles")
async def create_user_profile(profile_data: ProfileCreate, make_default: bool = False, user: dict = Depends(current_user)):
    try:
        data = profile_data.dict()
        profile_id = create_profile(user["id"], data, name=data.get("name", ""), make_default=make_default)
        return {"status": "success", "id": profile_id}
    except Exception as e:
        logger.error(f"Error creating profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to create profile")


@router.get("/profiles/{profile_id}")
async def get_user_profile_by_id(profile_id: int, user: dict = Depends(current_user)):
    profile = get_profile(user["id"], profile_id=profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/profiles/{profile_id}")
async def update_user_profile(profile_id: int, profile_data: ProfileCreate, user: dict = Depends(current_user)):
    if not update_profile_fields(user["id"], profile_id, profile_data.dict()):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success"}


@router.post("/profiles/{profile_id}/default")
async def make_profile_default(profile_id: int, user: dict = Depends(current_user)):
    if not set_default_profile(user["id"], profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success"}


@router.delete("/profiles/{profile_id}")
async def remove_user_profile(profile_id: int, user: dict = Depends(current_user)):
    try:
        if not delete_profile(user["id"], profile_id):
            raise HTTPException(status_code=404, detail="Profile not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success"}


@router.post("/profile/upload-resume")
async def upload_resume(file: UploadFile = File(...), apply_to_profile: bool = Form(True), profile_id: Optional[int] = Form(None), user: dict = Depends(current_user)):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > _MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="Resume file is too large (max 5 MB).")

    try:
        cv_text = extract_text_from_upload(file.filename or "", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Resume text extraction failed: {exc}")
        raise HTTPException(status_code=400, detail="Could not read text from this file. Try a .pdf, .docx, or .txt resume.")

    if not cv_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in the resume.")

    extracted = extract_profile_from_resume(cv_text, user["id"])
    extracted.pop("_ai_error", None)

    saved = False
    if apply_to_profile:
        existing = get_profile(user["id"], profile_id=profile_id) or {}
        merged = {**existing}
        for field in _RESUME_DERIVED_FIELDS:
            value = extracted.get(field)
            if value:
                merged[field] = value
        merged["resume_name"] = file.filename or merged.get("resume_name") or "resume"
        upsert_profile(merged, user["id"], profile_id=profile_id or (existing.get("id") if existing else None))
        saved = True

    return {
        "status": "success",
        "filename": file.filename,
        "applied_to_profile": saved,
        "characters": len(cv_text),
        "extracted": {field: extracted.get(field, "") for field in _RESUME_DERIVED_FIELDS},
    }
