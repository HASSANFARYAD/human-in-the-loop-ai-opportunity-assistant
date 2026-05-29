from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from job_assistant.config import settings

Base = declarative_base()


def _engine_kwargs() -> dict:
    if settings.effective_database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False, "timeout": 10}}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


engine = create_engine(settings.effective_database_url, future=True, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record):
    if not settings.effective_database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA busy_timeout=10000")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    cursor.close()


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def session_scope() -> Iterator:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    ip_address = Column(Text, nullable=True)
    resource_type = Column(Text, nullable=False)
    count = Column(Integer, nullable=False, default=0)
    window_start = Column(Text, nullable=False)
    window_end = Column(Text, nullable=False)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)


class SystemMetric(Base):
    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True)
    metric_name = Column(Text, nullable=False)
    metric_type = Column(Text, nullable=False, default="counter")
    value = Column(Float, nullable=False, default=0)
    labels_json = Column(Text)
    created_at = Column(Text, nullable=False)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True)
    severity = Column(Text, nullable=False, default="warning")
    title = Column(Text, nullable=False)
    message = Column(Text)
    source = Column(Text, nullable=False, default="system")
    metadata_json = Column(Text)
    status = Column(Text, nullable=False, default="open")
    created_at = Column(Text, nullable=False)
    acknowledged_at = Column(Text)


class WorkerJob(Base):
    __tablename__ = "worker_jobs"

    id = Column(Integer, primary_key=True)
    queue_name = Column(Text, nullable=False, default="default")
    job_type = Column(Text, nullable=False)
    payload_json = Column(Text)
    status = Column(Text, nullable=False, default="queued")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    locked_at = Column(Text)
    locked_by = Column(Text)
    run_after = Column(Text)
    last_error = Column(Text)
    created_at = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False)
    completed_at = Column(Text)


class ComplianceExport(Base):
    __tablename__ = "compliance_exports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    workspace_id = Column(Integer)
    export_type = Column(Text, nullable=False, default="user_data")
    status = Column(Text, nullable=False, default="completed")
    file_path = Column(Text, nullable=False)
    expires_at = Column(Text)
    created_at = Column(Text, nullable=False)


def sqlalchemy_health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database_url": settings.effective_database_url.split("@")[-1],
        "engine": engine.dialect.name,
    }
