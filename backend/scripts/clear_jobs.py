from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = str(Path(__file__).resolve().parents[1])
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely clear job/opportunity data while preserving users, profiles, auth, provider settings, and app config."
    )
    parser.add_argument("--user-id", type=int, help="Limit cleanup to one user id.")
    parser.add_argument("--confirm", action="store_true", help="Actually delete rows. Without this flag the script is a dry run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from job_assistant.db import clear_job_data

    result = clear_job_data(user_id=args.user_id, dry_run=not args.confirm)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not args.confirm:
        print("\nDry run only. Re-run with --confirm to delete these rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
