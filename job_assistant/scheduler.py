from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from job_assistant.db import due_reminders, get_profile, list_jobs
from job_assistant.services.gmail_ingest import fetch_job_alert_messages
from job_assistant.services.parsing import extract_job_from_text
from job_assistant.db import insert_job

logger = logging.getLogger(__name__)


class JobAssistantScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.is_running = False

    def start(self):
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        self._register_jobs()
        self.scheduler.start()
        self.is_running = True
        logger.info("Job Assistant Scheduler started")

    def stop(self):
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Job Assistant Scheduler stopped")

    def _register_jobs(self):
        # Check Gmail every 30 minutes for new job alerts
        self.scheduler.add_job(
            self._check_gmail_alerts,
            trigger=IntervalTrigger(minutes=30),
            id="gmail_check",
            name="Check Gmail for job alerts",
            replace_existing=True,
            max_instances=1,
        )

        # Check for due reminders every 5 minutes
        self.scheduler.add_job(
            self._check_reminders,
            trigger=IntervalTrigger(minutes=5),
            id="reminder_check",
            name="Check for due reminders",
            replace_existing=True,
            max_instances=1,
        )

        # Daily summary at 8 AM
        self.scheduler.add_job(
            self._daily_summary,
            trigger=CronTrigger(hour=8, minute=0),
            id="daily_summary",
            name="Generate daily summary",
            replace_existing=True,
            max_instances=1,
        )

        logger.info("Scheduler jobs registered")

    def _check_gmail_alerts(self):
        try:
            logger.info("Running Gmail check job")
            query = '("job alert" OR "new jobs" OR recruiter OR "is hiring") newer_than:1d'
            messages = fetch_job_alert_messages(query=query, max_results=20)

            if not messages:
                logger.info("No new Gmail job alerts")
                return

            count = 0
            for message in messages:
                try:
                    job = extract_job_from_text(
                        f"Subject: {message['subject']}\nFrom: {message['from']}\n\n{message['body']}",
                        source="Gmail"
                    )
                    job["date_received"] = message.get("date_received", "")
                    insert_job(job)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to process Gmail message: {e}")

            logger.info(f"Successfully imported {count} new job(s) from Gmail")
        except Exception as e:
            logger.error(f"Gmail check failed: {e}")

    def _check_reminders(self):
        try:
            reminders = due_reminders()
            if reminders:
                logger.info(f"Found {len(reminders)} due reminder(s)")
        except Exception as e:
            logger.error(f"Reminder check failed: {e}")

    def _daily_summary(self):
        try:
            jobs = list_jobs()
            profile = get_profile()

            if not profile:
                logger.info("No profile configured, skipping daily summary")
                return

            unscored = sum(1 for j in jobs if j.get("match_score") is None)
            applied = sum(1 for j in jobs if j.get("status") == "Applied")
            interviews = sum(1 for j in jobs if j.get("status") == "Interview")

            logger.info(
                f"Daily Summary: {len(jobs)} total jobs, "
                f"{unscored} unscored, {applied} applied, {interviews} interviews"
            )
        except Exception as e:
            logger.error(f"Daily summary failed: {e}")

    def add_custom_job(self, func, trigger, job_id, name):
        self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=name,
            replace_existing=True,
        )


# Global scheduler instance
_scheduler_instance = None


def get_scheduler():
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = JobAssistantScheduler()
    return _scheduler_instance


def start_scheduler():
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler():
    scheduler = get_scheduler()
    scheduler.stop()
