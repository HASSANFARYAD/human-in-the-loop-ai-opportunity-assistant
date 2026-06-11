#!/usr/bin/env python3
"""Restore a SQLite backup after creating a safety copy of the current DB."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore the app SQLite database from a backup file.")
    parser.add_argument("backup", help="Backup SQLite file to restore")
    parser.add_argument("--db", default="data/job_assistant.sqlite3", help="Destination app database path")
    args = parser.parse_args()

    backup = Path(args.backup)
    dest = Path(args.db)
    if not backup.exists():
        raise SystemExit(f"Backup not found: {backup}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safety_copy = dest.with_suffix(dest.suffix + f".pre_restore_{stamp}")
        shutil.copy2(dest, safety_copy)
        print(f"Safety copy created: {safety_copy}")

    shutil.copy2(backup, dest)
    print(f"Restored {backup} -> {dest}")


if __name__ == "__main__":
    main()
