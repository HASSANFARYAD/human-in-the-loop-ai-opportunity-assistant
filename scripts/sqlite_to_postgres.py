#!/usr/bin/env python3
from __future__ import annotations

"""Best-effort SQLite to PostgreSQL migration helper.

Usage:
  DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db python scripts/sqlite_to_postgres.py --sqlite data/job_assistant.sqlite3

The app still runs SQLite-first in MVP mode. Use this after provisioning a
PostgreSQL database and applying Alembic migrations.
"""

import argparse
import os
import sqlite3
from sqlalchemy import create_engine, text

TABLES = [
    "users", "profile", "jobs", "evaluations", "applications", "application_materials", "reminders",
    "integration_settings", "provider_configs", "feedback", "audit_logs", "activity_events",
    "ai_generations", "prompt_versions", "automation_rules", "automation_runs", "automation_steps", "automation_errors",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=os.getenv("APP_DB_PATH", "data/job_assistant.sqlite3"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")
    sqlite = sqlite3.connect(args.sqlite)
    sqlite.row_factory = sqlite3.Row
    engine = create_engine(args.database_url, pool_pre_ping=True)
    copied = {}
    with engine.begin() as pg:
        for table in TABLES:
            try:
                rows = sqlite.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                continue
            if not rows:
                copied[table] = 0
                continue
            keys = rows[0].keys()
            cols = ", ".join(keys)
            params = ", ".join(f":{k}" for k in keys)
            stmt = text(f"INSERT INTO {table} ({cols}) VALUES ({params})")
            pg.execute(stmt, [dict(r) for r in rows])
            copied[table] = len(rows)
    print(copied)


if __name__ == "__main__":
    main()
