from job_assistant.routes.health import router as health_router
from job_assistant.routes.auth import router as auth_router
from job_assistant.routes.profiles import router as profiles_router
from job_assistant.routes.jobs import router as jobs_router
from job_assistant.routes.discovery import router as discovery_router
from job_assistant.routes.agent import router as agent_router
from job_assistant.routes.admin import router as admin_router
from job_assistant.routes.enterprise import router as enterprise_router
from job_assistant.routes.automation import router as automation_router
from job_assistant.routes.recordings import router as recordings_router
from job_assistant.routes.gmail import router as gmail_router
from job_assistant.routes.integrations import router as integrations_router
from job_assistant.routes.feedback import router as feedback_router
from job_assistant.routes.publishing import router as publishing_router
from job_assistant.routes.compliance import router as compliance_router
from job_assistant.routes.monitoring import router as monitoring_router
from job_assistant.routes.linkedin import router as linkedin_router

all_routers = [
    health_router,
    auth_router,
    profiles_router,
    jobs_router,
    discovery_router,
    agent_router,
    admin_router,
    enterprise_router,
    automation_router,
    recordings_router,
    gmail_router,
    integrations_router,
    feedback_router,
    publishing_router,
    compliance_router,
    monitoring_router,
    linkedin_router,
]
