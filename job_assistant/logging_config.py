import logging
import logging.handlers
import sys
from pathlib import Path

from job_assistant.config import settings


def setup_logging():
    Path("logs").mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if settings.log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logging.getLogger("streamlit").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


setup_logging()
