from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from job_assistant.db import (
    add_activity_event,
    due_reminders,
    get_automation_preferences,
    get_integration_settings,
    get_profile,
    insert_job,
    list_jobs,
    save_evaluation,
    save_materials,
)
from job_assistant.services.generation import generate_materials
from job_assistant.services.gmail_ingest import fetch_job_alert_messages
from job_assistant.services.parsing import extract_job_from_text
from job_assistant.services.opportunity_classifier import extract_opportunities_from_container, scoring_gate
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.rapidapi_linkedin import (
    DEFAULT_ENDPOINT as RAPIDAPI_LINKEDIN_ENDPOINT,
    DEFAULT_HOST as RAPIDAPI_LINKEDIN_HOST,
    rapidapi_items_to_opportunities,
    search_linkedin_jobs,
)
from job_assistant.services.linkedin_integration import search_linkedin_jobs_official
from job_assistant.services.scoring import score_job
from job_assistant.services.loops import check_and_run_due_loops

logger = logging.getLogger(__name__)


class JobAssistantScheduler:
    def __init__(self, user_id: int = 1):
        self.user_id = user_id
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
        prefs = get_automation_preferences(self.user_id)
        gmail_minutes = max(5, int(prefs.get("gmail_interval_minutes", 30)))
        public_hours = max(1, int(prefs.get("public_interval_hours", 6)))
        linkedin_hours = max(1, int(prefs.get("linkedin_interval_hours", 6)))
        summary_hour = min(23, max(0, int(prefs.get("daily_summary_hour", 8))))

        # Check Gmail on the user's preferred interval
        self.scheduler.add_job(
            self._check_gmail_alerts,
            trigger=IntervalTrigger(minutes=gmail_minutes),
            id="gmail_check",
            name="Check Gmail for job alerts",
            replace_existing=True,
            max_instances=1,
        )

        # Pull LinkedIn jobs from RapidAPI on the user's preferred interval
        self.scheduler.add_job(
            self._check_linkedin_api,
            trigger=IntervalTrigger(hours=linkedin_hours),
            id="linkedin_api_check",
            name="Check RapidAPI LinkedIn jobs",
            replace_existing=True,
            max_instances=1,
        )

        # Pull LinkedIn jobs from the official LinkedIn API on the user's preferred interval
        self.scheduler.add_job(
            self._check_linkedin_official_api,
            trigger=IntervalTrigger(hours=linkedin_hours),
            id="linkedin_official_api_check",
            name="Check official LinkedIn Jobs API",
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

        # Pull public no-auth job APIs on the user's preferred interval
        self.scheduler.add_job(
            self._check_public_sources,
            trigger=IntervalTrigger(hours=public_hours),
            id="public_source_check",
            name="Check public opportunity sources",
            replace_existing=True,
            max_instances=1,
        )

        # Run due auto-pilot loops every 30 minutes
        self.scheduler.add_job(
            self._check_loops,
            trigger=IntervalTrigger(minutes=30),
            id="loop_check",
            name="Check and run due auto-pilot loops",
            replace_existing=True,
            max_instances=1,
        )

        # Daily summary at the user's preferred hour
        self.scheduler.add_job(
            self._daily_summary,
            trigger=CronTrigger(hour=summary_hour, minute=0),
            id="daily_summary",
            name="Generate daily summary",
            replace_existing=True,
            max_instances=1,
        )

        logger.info("Scheduler jobs registered")

    def _process_new_opportunity(self, opportunity: dict) -> int:
        gate = scoring_gate(opportunity)
        if not gate.importable:
            raise ValueError(gate.blocked_reason or "Non-opportunity content cannot be imported or scored")
        job_id = insert_job(opportunity, self.user_id)
        prefs = get_automation_preferences(self.user_id)
        profile = get_profile(self.user_id)
        if profile and prefs.get("score_new"):
            evaluation = score_job(profile, opportunity, user_id=self.user_id)
            save_evaluation(job_id, evaluation, self.user_id)
            if prefs.get("generate_materials") and int(evaluation.get("match_score", 0)) >= int(prefs.get("min_score_for_materials", 70)) and opportunity.get("opportunity_type", "job") == "job":
                materials = generate_materials(profile, opportunity, evaluation, user_id=self.user_id)
                save_materials(job_id, materials, self.user_id)
        return job_id

    def _check_gmail_alerts(self):
        try:
            prefs = get_automation_preferences(self.user_id)
            if not prefs.get("enabled") or not prefs.get("gmail_enabled"):
                logger.info("Gmail automation disabled")
                return
            logger.info("Running Gmail check job")
            query = '("job alert" OR "new jobs" OR recruiter OR "is hiring" OR hackathon OR webinar OR competition OR contest OR challenge) newer_than:1d'
            messages = fetch_job_alert_messages(user_id=self.user_id, query=query, max_results=20)

            if not messages:
                logger.info("No new Gmail job alerts")
                return

            count = 0
            for message in messages:
                try:
                    source_item = {
                        "title": message.get("subject", ""),
                        "subject": message.get("subject", ""),
                        "sender": message.get("from", ""),
                        "snippet": message.get("snippet", ""),
                        "body": message.get("body", ""),
                        "source": "Gmail",
                        "source_type": "gmail",
                        "message_id": message.get("message_id", ""),
                        "open_url": message.get("open_url", ""),
                    }
                    extracted = extract_opportunities_from_container(source_item)
                    candidates = extracted or [
                        extract_job_from_text(
                            f"Subject: {message['subject']}\nFrom: {message['from']}\n\n{message['body']}",
                            source="Gmail",
                            opportunity_type="auto",
                            user_id=self.user_id,
                        )
                    ]
                    for job in candidates:
                        job["date_received"] = message.get("date_received", "")
                        job["source_email_id"] = message.get("message_id", "")
                        job["source_email_open_url"] = message.get("open_url", "")
                        self._process_new_opportunity(job)
                        count += 1
                except Exception as e:
                    logger.error(f"Failed to process Gmail message: {e}")

            add_activity_event(self.user_id, "Gmail import complete", f"Imported {count} new opportunity/opportunities from Gmail.")
            logger.info(f"Successfully imported {count} new job(s) from Gmail")
        except Exception as e:
            add_activity_event(self.user_id, "Gmail import failed", str(e), level="error")
            logger.error(f"Gmail check failed: {e}")

    def _check_public_sources(self):
        try:
            prefs = get_automation_preferences(self.user_id)
            if not prefs.get("enabled") or not prefs.get("public_sources_enabled"):
                logger.info("Public source automation disabled")
                return
            profile = get_profile(self.user_id)
            query = " ".join(
                str(profile.get(key, ""))
                for key in ["target_roles", "skills", "industries"]
                if profile.get(key)
            ).strip()
            if not query:
                logger.info("No profile keywords configured, skipping public source discovery")
                return

            logger.info("Running public source discovery")
            opportunities = discover_public_opportunities(
                query=query,
                sources=["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"],
                limit_per_source=20,
            )
            count = 0
            for opportunity in opportunities:
                self._process_new_opportunity(opportunity)
                count += 1
            add_activity_event(self.user_id, "Public discovery complete", f"Imported {count} public opportunity/opportunities.")
            logger.info(f"Imported {count} public opportunity/opportunities")
        except Exception as e:
            add_activity_event(self.user_id, "Public discovery failed", str(e), level="error")
            logger.error(f"Public source discovery failed: {e}")


    def _check_linkedin_api(self):
        try:
            prefs = get_automation_preferences(self.user_id)
            if not prefs.get("enabled") or not prefs.get("linkedin_api_enabled"):
                logger.info("LinkedIn API automation disabled")
                return

            rapidapi = get_integration_settings(self.user_id, "rapidapi_linkedin")
            rapidapi_key = rapidapi.get("api_key", "")
            rapidapi_config = rapidapi.get("config", {})
            if not rapidapi_key:
                add_activity_event(self.user_id, "LinkedIn API skipped", "Add a RapidAPI LinkedIn key in Integrations first.", level="warning")
                return

            profile = get_profile(self.user_id) or {}
            title_filter = rapidapi_config.get("title_filter") or profile.get("target_roles") or profile.get("skills") or "software engineer"
            location_filter = rapidapi_config.get("location_filter") or profile.get("locations") or "Remote"
            max_offsets = max(1, int(rapidapi_config.get("max_offsets", 1)))

            imported = 0
            for offset in range(max_offsets):
                items = search_linkedin_jobs(
                    rapidapi_key,
                    title_filter,
                    location_filter,
                    offset,
                    rapidapi_config.get("host", RAPIDAPI_LINKEDIN_HOST),
                    rapidapi_config.get("endpoint", RAPIDAPI_LINKEDIN_ENDPOINT),
                )
                for opportunity in rapidapi_items_to_opportunities(items):
                    self._process_new_opportunity(opportunity)
                    imported += 1

            add_activity_event(
                self.user_id,
                "LinkedIn API import complete",
                f"Imported {imported} LinkedIn opportunity/opportunities for '{title_filter}' in '{location_filter}'.",
            )
            logger.info("Imported %s LinkedIn API opportunity/opportunities", imported)
        except Exception as e:
            add_activity_event(self.user_id, "LinkedIn API import failed", str(e), level="error")
            logger.error(f"LinkedIn API import failed: {e}")


    def _check_linkedin_official_api(self):
        try:
            prefs = get_automation_preferences(self.user_id)
            if not prefs.get("enabled") or not prefs.get("linkedin_api_enabled"):
                logger.info("LinkedIn Official API automation disabled")
                return

            from job_assistant.services.linkedin_integration import _credentials_for_user as _li_creds
            try:
                credentials = _li_creds(self.user_id)
            except RuntimeError:
                return
            access_token = credentials.get("access_token", "")
            if not access_token:
                return

            profile = get_profile(self.user_id) or {}
            title_filter = profile.get("target_roles") or profile.get("skills") or "software engineer"
            location_filter = profile.get("locations") or "Remote"

            items = search_linkedin_jobs_official(access_token, title_filter, location_filter, 0, 25)
            imported = 0
            for item in items:
                self._process_new_opportunity(item)
                imported += 1

            if imported:
                add_activity_event(
                    self.user_id,
                    "LinkedIn Official API import complete",
                    f"Imported {imported} opportunities for '{title_filter}' in '{location_filter}'.",
                )
                logger.info("Imported %s from LinkedIn Official API", imported)
        except RuntimeError as e:
            if "Recruiter" in str(e) or "license" in str(e):
                logger.info("LinkedIn Official Jobs API not available for this user: %s", e)
            else:
                add_activity_event(self.user_id, "LinkedIn Official API import failed", str(e)[:200], level="error")
                logger.error("LinkedIn Official API import failed: %s", e)
        except Exception as e:
            add_activity_event(self.user_id, "LinkedIn Official API import failed", str(e)[:200], level="error")
            logger.error("LinkedIn Official API import failed: %s", e)


    def _check_reminders(self):
        try:
            reminders = due_reminders(self.user_id)
            if reminders:
                add_activity_event(self.user_id, "Reminders due", f"You have {len(reminders)} reminder(s) due.")
                logger.info(f"Found {len(reminders)} due reminder(s)")
        except Exception as e:
            logger.error(f"Reminder check failed: {e}")

    def _check_loops(self):
        try:
            prefs = get_automation_preferences(self.user_id)
            if not prefs.get("enabled"):
                logger.info("Automation disabled, skipping loop check")
                return
            results = check_and_run_due_loops(self.user_id)
            completed = sum(1 for r in results if r.get("status") == "completed")
            failed = sum(1 for r in results if r.get("status") in ("error", "failed"))
            budget_exhausted = sum(1 for r in results if r.get("status") == "budget_exhausted")
            if results:
                logger.info("Loop check complete: %d completed, %d failed, %d budget exhausted", completed, failed, budget_exhausted)
                from job_assistant.db import add_activity_event
                add_activity_event(self.user_id, "Auto-pilot loop check", f"{completed} loops completed, {failed} failed, {budget_exhausted} budget exhausted")
        except Exception as e:
            logger.error("Loop check failed: %s", e)

    def _daily_summary(self):
        try:
            jobs = list_jobs(self.user_id)
            profile = get_profile(self.user_id)

            if not profile:
                logger.info("No profile configured, skipping daily summary")
                return

            unscored = sum(1 for j in jobs if j.get("match_score") is None)
            applied = sum(1 for j in jobs if j.get("status") == "Applied")
            interviews = sum(1 for j in jobs if j.get("status") == "Interview")

            message = f"{len(jobs)} total opportunities, {unscored} unscored, {applied} applied, {interviews} interviews"
            add_activity_event(self.user_id, "Daily summary", message)
            logger.info(f"Daily Summary: {message}")
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


# Global scheduler instances keyed by user id.
_scheduler_instances: dict[int, JobAssistantScheduler] = {}


def get_scheduler(user_id: int = 1):
    if user_id not in _scheduler_instances:
        _scheduler_instances[user_id] = JobAssistantScheduler(user_id)
    return _scheduler_instances[user_id]


def start_scheduler(user_id: int = 1):
    scheduler = get_scheduler(user_id)
    scheduler.start()


def stop_scheduler(user_id: int | None = None):
    if user_id is not None:
        get_scheduler(user_id).stop()
        return
    for scheduler in _scheduler_instances.values():
        scheduler.stop()
