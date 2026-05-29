from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from job_assistant import api
from job_assistant.config import settings
from job_assistant.logging_config import setup_logging
from job_assistant.observability import observability_middleware
from job_assistant.rate_limits import sqlite_rate_limit_middleware
from job_assistant.runtime import validate_startup_configuration

setup_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(sqlite_rate_limit_middleware)
    app.middleware("http")(observability_middleware)

    app.include_router(api.router)

    @app.on_event("startup")
    async def startup_event():
        logger.info(f"Starting {settings.app_name} in {settings.environment} mode with {settings.deployment_profile} deployment profile")
        validate_startup_configuration(strict=settings.is_production)
        if settings.scheduler_enabled:
            try:
                from job_assistant.scheduler import start_scheduler
                start_scheduler()
            except Exception as e:
                logger.error(f"Failed to start scheduler: {e}")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info(f"Shutting down {settings.app_name}")
        if settings.scheduler_enabled:
            try:
                from job_assistant.scheduler import stop_scheduler
                stop_scheduler()
            except Exception as e:
                logger.error(f"Failed to stop scheduler: {e}")

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        error_id = uuid.uuid4().hex[:12]
        logger.error(f"Unhandled exception [{error_id}]: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error_id": error_id},
        )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )
