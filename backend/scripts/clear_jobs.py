from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely clear job/opportunity data while preserving users, profiles, auth, provider settings, and app config."
    )
    parser.add_argument("--db", help="SQLite database path. Defaults to APP_DB_PATH/settings.")
    parser.add_argument("--user-id", type=int, help="Limit cleanup to one user id.")
    parser.add_argument("--confirm", action="store_true", help="Actually delete rows. Without this flag the script is a dry run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.db:
        os.environ["APP_DB_PATH"] = args.db

    from job_assistant.db import clear_job_data, db_path

    result = clear_job_data(user_id=args.user_id, dry_run=not args.confirm)
    result["database_path"] = str(db_path())
    print(json.dumps(result, indent=2, sort_keys=True))
    if not args.confirm:
        print("\nDry run only. Re-run with --confirm to delete these rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
