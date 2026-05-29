# Phase 6 - PostgreSQL Migration Readiness

Implemented readiness items:

- Alembic configuration and first migration file.
- `DATABASE_URL` support remains present in configuration.
- PostgreSQL dependency already included through `psycopg2-binary` and SQLAlchemy.
- SQLite-to-PostgreSQL migration helper added at `scripts/sqlite_to_postgres.py`.
- New Phase 4/5 tables use portable column types.

Important limitation:

The runtime application still uses the compact SQLite helper layer for core reads/writes. Full PostgreSQL runtime mode requires replacing those helper calls with SQLAlchemy sessions or adding a compatibility repository layer. This package completes migration readiness, not a full database engine swap.

Recommended next step:

- Introduce a SQLAlchemy repository layer for users, jobs, feedback, integrations, providers, AI logs, and automation runs.
- Run the app in staging against PostgreSQL after repository parity tests pass.
