"""Automated MongoDB database backups.

Runs on a dedicated APScheduler instance, independent of the automation
scheduler (``SCHEDULER_ENABLED``). Each run dumps all collections to a
timestamped JSON file using pymongo, prunes old local copies beyond the
retention window, and optionally uploads the snapshot to an S3-compatible
bucket (e.g. Cloudflare R2).
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from job_assistant.config import settings
from job_assistant.db import MONGO_URL, MONGO_DB_NAME, get_db

logger = logging.getLogger(__name__)

_BACKUP_GLOB = "job_assistant_*.json"


def create_backup() -> Path:
    """Export all MongoDB collections to a timestamped JSON file. Returns the path."""
    out_dir = Path(settings.backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"job_assistant_{stamp}.json"

    db = get_db()
    backup_data = {}
    for name in db.list_collection_names():
        if name == "counters":
            continue
        docs = list(db[name].find({}, {"_id": False}))
        if docs:
            backup_data[name] = docs

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, default=str, indent=2)

    logger.info("MongoDB backup created: %s (%d collections)", dest, len(backup_data))
    return dest


def prune_old_backups() -> int:
    """Delete local backups beyond the retention count. Returns number removed."""
    retention = settings.backup_retention
    if retention <= 0:
        return 0
    out_dir = Path(settings.backup_dir)
    if not out_dir.exists():
        return 0
    backups = sorted(out_dir.glob(_BACKUP_GLOB), key=lambda p: p.name, reverse=True)
    removed = 0
    for stale in backups[retention:]:
        try:
            stale.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("Failed to prune backup %s: %s", stale, exc)
    if removed:
        logger.info("Pruned %d old backup(s)", removed)
    return removed


def upload_to_s3(path: Path) -> bool:
    """Upload a backup to the configured S3-compatible bucket. No-op if unconfigured."""
    if not settings.backup_s3_bucket:
        return False
    try:
        import boto3
    except ModuleNotFoundError:
        logger.error("BACKUP_S3_BUCKET set but boto3 is not installed; skipping offsite upload.")
        return False

    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.backup_s3_endpoint or None,
            aws_access_key_id=settings.backup_s3_access_key or None,
            aws_secret_access_key=settings.backup_s3_secret_key or None,
        )
        key = f"{settings.backup_s3_prefix.strip('/')}/{path.name}" if settings.backup_s3_prefix else path.name
        client.upload_file(str(path), settings.backup_s3_bucket, key)
        logger.info("Backup uploaded to s3://%s/%s", settings.backup_s3_bucket, key)
        return True
    except Exception as exc:  # network/credential failures must not crash the job
        logger.error("Offsite backup upload failed: %s", exc)
        return False


def run_backup() -> Optional[Path]:
    """Full backup cycle: snapshot, optional upload, prune. Never raises."""
    try:
        dest = create_backup()
        upload_to_s3(dest)
        prune_old_backups()
        return dest
    except Exception as exc:
        logger.error("Database backup failed: %s", exc, exc_info=True)
        return None


_scheduler: Optional[BackgroundScheduler] = None


def start_backup_scheduler() -> None:
    global _scheduler
    if not settings.backup_enabled:
        logger.info("Automated backups disabled (BACKUP_ENABLED=false)")
        return
    if _scheduler is not None:
        logger.warning("Backup scheduler already running")
        return
    interval = max(1, settings.backup_interval_hours)
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_backup,
        trigger=IntervalTrigger(hours=interval),
        id="db_backup",
        name="Automated database backup",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),
    )
    _scheduler.start()
    logger.info("Backup scheduler started (every %dh, retention=%d)", interval, settings.backup_retention)


def stop_backup_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Backup scheduler stopped")
