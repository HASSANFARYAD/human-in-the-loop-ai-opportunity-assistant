"""
Standalone background worker process for the job queue.

Run:
    python worker_entry.py [--queue default] [--poll 5]

Optional:    pip install -r requirements-optional.txt

The worker polls 'worker_jobs' table, claims available jobs,
dispatches them to registered handlers, and records results.

Extend by adding handlers to JOB_HANDLERS dict.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from typing import Any, Callable

from job_assistant.config import settings
from job_assistant.logging_config import setup_logging
from job_assistant.worker_queue import claim_next_job, complete_job, fail_job

setup_logging()
logger = logging.getLogger("worker")

SHUTDOWN = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global SHUTDOWN
    SHUTDOWN = True
    logger.info("Shutdown signal received, finishing current job...")


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


JOB_HANDLERS: dict[str, Callable[[dict[str, Any]], None]] = {
    # Examples:
    # "email_digest": handle_email_digest,
    # "scrape_opportunity": handle_scrape_opportunity,
}


def run_worker(queue_name: str = "default", poll_interval: int = 5) -> None:
    logger.info("Worker started (queue=%s, poll=%ss)", queue_name, poll_interval)

    while not SHUTDOWN:
        job = claim_next_job(queue_name=queue_name, worker_id=f"worker-{queue_name}")
        if not job:
            time.sleep(poll_interval)
            continue

        job_id = job["id"]
        job_type = job["job_type"]
        payload = job.get("payload", {})
        logger.info("Claimed job %s (type=%s)", job_id, job_type)

        handler = JOB_HANDLERS.get(job_type)
        if not handler:
            logger.warning("No handler registered for job_type=%s, marking as failed", job_type)
            fail_job(job_id, f"No handler for job type: {job_type}")
            continue

        try:
            handler(payload)
            complete_job(job_id)
            logger.info("Completed job %s", job_id)
        except Exception as exc:
            logger.exception("Job %s failed: %s", job_id, exc)
            fail_job(job_id, str(exc)[:1000])

    logger.info("Worker shut down gracefully")


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Assistant background worker")
    parser.add_argument("--queue", default="default", help="Queue name to poll")
    parser.add_argument("--poll", type=int, default=5, help="Poll interval in seconds")
    args = parser.parse_args()

    logger.info("Initializing worker environment")
    run_worker(queue_name=args.queue, poll_interval=args.poll)


if __name__ == "__main__":
    main()
