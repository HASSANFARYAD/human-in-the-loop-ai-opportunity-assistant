from __future__ import annotations

import logging
from pathlib import Path

from job_assistant.config import settings

logger = logging.getLogger(__name__)


def validate_startup_configuration(strict: bool = False) -> list[str]:
    """Return deployment warnings and optionally fail on production misconfiguration."""
    settings.ensure_runtime_dirs()
    warnings = settings.startup_warnings()
    for warning in warnings:
        logger.warning("Startup configuration warning: %s", warning)
    if strict and warnings:
        raise RuntimeError("Invalid production configuration: " + "; ".join(warnings))
    return warnings


def runtime_status() -> dict:
    db_file = Path(settings.db_path)
    return {
        **settings.public_runtime_info(),
        "data_dir_exists": Path(settings.app_data_dir).exists(),
        "log_dir_exists": Path(settings.log_dir).exists(),
        "sqlite_db_exists": db_file.exists() if not settings.database_url else None,
        "warnings": settings.startup_warnings(),
    }
