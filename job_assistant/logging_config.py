import logging
import logging.handlers
import sys
from pathlib import Path

from job_assistant.config import settings


def setup_logging():
    settings.ensure_runtime_dirs()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())

    # Avoid duplicate handlers when Streamlit reloads modules.
    if not any(getattr(handler, "_job_assistant_handler", False) for handler in root_logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler._job_assistant_handler = True
        root_logger.addHandler(console_handler)

    if settings.log_file and not any(isinstance(handler, logging.handlers.RotatingFileHandler) and getattr(handler, "baseFilename", "") == str(Path(settings.log_file).resolve()) for handler in root_logger.handlers):
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_file,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
        )
        file_handler.setFormatter(formatter)
        file_handler._job_assistant_handler = True
        root_logger.addHandler(file_handler)

    logging.getLogger("streamlit").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


setup_logging()
