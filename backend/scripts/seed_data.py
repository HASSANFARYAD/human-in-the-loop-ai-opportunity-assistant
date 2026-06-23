from __future__ import annotations

"""Seed the database with a demo user, profile, and sample opportunities.

Idempotent: re-running reuses the existing demo user and skips jobs whose
URL already exists for that user. Uses the centralized seed_demo_data()
from the db module.

Examples:
    python scripts/seed_data.py
"""

import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main() -> int:
    from job_assistant.db import init_db, needs_seed, seed_demo_data

    init_db()

    if needs_seed():
        seed_demo_data()
        print("Database seeded with demo data.")
    else:
        print("Database already contains data — skipping seed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
