#!/usr/bin/env python3
"""Create a timestamped SQLite backup using SQLite's online backup API."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the app SQLite database.")
    parser.add_argument("--db", default="data/job_assistant.sqlite3", help="Source SQLite database path")
    parser.add_argument("--out-dir", default="backups", help="Backup output directory")
    args = parser.parse_args()

    src = Path(args.db)
    if not src.exists():
        raise SystemExit(f"Database not found: {src}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"job_assistant_{stamp}.sqlite3"

    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)

    print(dest)


if __name__ == "__main__":
    main()
