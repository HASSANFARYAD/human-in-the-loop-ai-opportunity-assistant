from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from job_assistant.auth import authenticate_user, create_access_token, current_user, public_user, register_user
from job_assistant.db import (
    create_reminder,
    delete_job,
    delete_user_data,
    due_reminders,
    get_evaluation,
    get_job,
    get_materials,
    get_profile,
    insert_job,
    list_jobs,
    save_evaluation,
    save_materials,
    update_status,
    upsert_profile,
)
from job_assistant.services.generation import generate_materials
from job_assistant.services.scoring import score_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


class ProfileCreate(BaseModel):
    cv_text: str
    target_roles: str
    industries: str
    locations: str
    remote_preference: str
    salary_expectations: str
    work_authorization: str
    years_experience: str
    skills: str
    deal_breakers: str


class JobCreate(BaseModel):
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    remote_type: Optional[str] = None
    url: Optional[str] = None
    source: str
    description: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    deadline: Optional[str] = None
    opportunity_type: str = "job"


class ReminderCreate(BaseModel):
    job_id: int
    kind: str
    remind_at: str
    note: Optional[str] = None


class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str = ""


class UserLogin(BaseModel):
    email: str
    password: str


@router.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.post("/auth/register")
async def register(user_data: UserRegister):
    if len(user_data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    try:
        user = register_user(user_data.email, user_data.password, user_data.full_name)
        token = create_access_token(user)
        return {"access_token": token, "token_type": "bearer", "user": public_user(user)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail="Failed to register user")


@router.post("/auth/login")
async def login(login_data: UserLogin):
    user = authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


@router.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)


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


@router.get("/jobs")
async def list_all_jobs(user: dict = Depends(current_user)):
    try:
        jobs = list_jobs(user["id"])
        return jobs
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list jobs")


@router.post("/jobs")
async def create_job(job_data: JobCreate, user: dict = Depends(current_user)):
    try:
        job_id = insert_job(job_data.dict(), user["id"])
        return {"id": job_id, "status": "success", "message": "Job created"}
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job")


@router.get("/jobs/{job_id}")
async def get_job_detail(job_id: int, user: dict = Depends(current_user)):
    try:
        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to get job")


@router.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: int, user: dict = Depends(current_user)):
    try:
        delete_job(job_id, user["id"])
        return {"status": "success", "message": "Opportunity deleted"}
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete job")


@router.post("/jobs/{job_id}/score")
async def score_single_job(job_id: int, user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"])
        if not profile:
            raise HTTPException(status_code=400, detail="Profile not configured")

        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        evaluation = score_job(profile, job)
        save_evaluation(job_id, evaluation, user["id"])
        return evaluation
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scoring job: {e}")
        raise HTTPException(status_code=500, detail="Failed to score job")


@router.post("/jobs/{job_id}/generate-materials")
async def generate_job_materials(job_id: int, user: dict = Depends(current_user)):
    try:
        profile = get_profile(user["id"])
        if not profile:
            raise HTTPException(status_code=400, detail="Profile not configured")

        job = get_job(job_id, user["id"])
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        evaluation = get_evaluation(job_id, user["id"])
        if not evaluation:
            evaluation = score_job(profile, job)
            save_evaluation(job_id, evaluation, user["id"])

        materials = generate_materials(profile, job, evaluation, user_id=user["id"])
        save_materials(job_id, materials, user["id"])
        return materials
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating materials: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate materials")


@router.get("/jobs/{job_id}/materials")
async def get_job_materials(job_id: int, user: dict = Depends(current_user)):
    try:
        materials = get_materials(job_id, user["id"])
        return materials or {}
    except Exception as e:
        logger.error(f"Error getting materials: {e}")
        raise HTTPException(status_code=500, detail="Failed to get materials")


@router.patch("/jobs/{job_id}/status")
async def update_job_status(job_id: int, status: str, notes: str = "", user: dict = Depends(current_user)):
    try:
        update_status(job_id, status, notes, user["id"])
        return {"status": "success", "message": "Job status updated"}
    except Exception as e:
        logger.error(f"Error updating status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update status")


@router.get("/reminders")
async def list_reminders(user: dict = Depends(current_user)):
    try:
        reminders = due_reminders(user["id"])
        return reminders
    except Exception as e:
        logger.error(f"Error listing reminders: {e}")
        raise HTTPException(status_code=500, detail="Failed to list reminders")


@router.post("/reminders")
async def create_reminder_endpoint(reminder_data: ReminderCreate, user: dict = Depends(current_user)):
    try:
        create_reminder(
            reminder_data.job_id,
            reminder_data.kind,
            reminder_data.remind_at,
            reminder_data.note or "",
            user["id"],
        )
        return {"status": "success", "message": "Reminder created"}
    except Exception as e:
        logger.error(f"Error creating reminder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create reminder")


@router.post("/data/clear")
async def clear_my_data(user: dict = Depends(current_user)):
    try:
        delete_user_data(user["id"])
        return {"status": "success", "message": "Your data was deleted"}
    except Exception as e:
        logger.error(f"Error clearing data: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear data")
