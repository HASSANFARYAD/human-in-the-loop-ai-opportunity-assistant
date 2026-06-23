"""Automated follow-up reminders.

Runs on a dedicated APScheduler instance (independent of the automation
scheduler ``SCHEDULER_ENABLED``). Each run creates reminders for applications
stuck in 'Applied' with no status change in ``FOLLOWUP_AFTER_DAYS`` days.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from job_assistant.config import settings
from job_assistant.db import create_followup_reminders

logger = logging.getLogger(__name__)


def run_followups() -> int:
    """Create follow-up reminders for stale applications. Never raises."""
    try:
        created = create_followup_reminders(after_days=settings.followup_after_days)
        if created:
            logger.info("Created %d follow-up reminder(s)", created)
        return created
    except Exception as exc:
        logger.error("Follow-up reminder job failed: %s", exc, exc_info=True)
        return 0


_scheduler: Optional[BackgroundScheduler] = None


def start_followup_scheduler() -> None:
    global _scheduler
    if not settings.followup_reminders_enabled:
        logger.info("Automated follow-up reminders disabled (FOLLOWUP_REMINDERS_ENABLED=false)")
        return
    if _scheduler is not None:
        logger.warning("Follow-up scheduler already running")
        return
    interval = max(1, settings.followup_interval_hours)
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_followups,
        trigger=IntervalTrigger(hours=interval),
        id="followup_reminders",
        name="Automated follow-up reminders",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),  # run once on boot
    )
    _scheduler.start()
    logger.info("Follow-up scheduler started (every %dh, after %d days)", interval, settings.followup_after_days)


def stop_followup_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Follow-up scheduler stopped")
