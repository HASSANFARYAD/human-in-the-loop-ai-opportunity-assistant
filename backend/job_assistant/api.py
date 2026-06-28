from __future__ import annotations

from fastapi import APIRouter

from job_assistant.routes import all_routers
from job_assistant.routes.jobs import (
    _generate_interview_prep,
    _generate_tailored_resume,
)

router = APIRouter(prefix="/api/v1")

for sub_router in all_routers:
    router.include_router(sub_router)
