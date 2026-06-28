# Documentation Changelog

## Phase 2 — June 2026

### New Files Created

| File | Description |
|------|-------------|
| `ARCHITECTURE.md` | Complete backend architecture: module structure, services layer, request flow, AI routing, frontend routes, 35+ MongoDB collections, external integrations. New file (was missing entirely). |
| `FEATURE_MATRIX.md` | 80+ features with implementation status, completion %, and evidence file references. Replaces informal notes with structured audit. |
| `KNOWN_LIMITATIONS.md` | Missing features, partial implementations, technical debt, security/perf/third-party limitations. Previously undocumented. |
| `API_ENDPOINTS.md` | All 80+ REST endpoints organized by domain with authentication requirements. Previously undocumented. |
| `CONFIGURATION.md` | All environment variables with defaults and descriptions, plus AI provider parameters. Previously undocumented. |
| `TESTING.md` | Test file inventory, coverage gaps, runner commands, mocking strategy. Previously undocumented. |
| `DOCUMENTATION_CHANGELOG.md` | This file — tracks all documentation changes. |

### Existing Files Fixed

| File | Changes |
|------|---------|
| `README.md` | Removed all SQLite references; corrected primary datastore to MongoDB; updated dedup description to include fuzzy matching; fixed deployment guidance to match actual dependencies. |
| `DEPLOYMENT.md` | Rewritten — removed all SQLite references, corrected to MongoDB-only deployment, removed stale config values, added actual dependency list. |

### Existing Files Fixed (Phase 2 Cleanup)

| File | Changes |
|------|---------|
| `PRODUCT_AND_ARCHITECTURE.md` | Rewrote §8 Data Model (was "SQLite + MongoDB" → MongoDB-only); removed SQLite from architecture diagram, cross-cutting modules, tech stack, and §12 notes. 6 edits total. |
| `PENDING_FEATURES.md` | Expanded from 2 items to 8 with priority levels; references new comprehensive docs (`FEATURE_MATRIX.md`, `KNOWN_LIMITATIONS.md`). |
| `job-assistant-overview.html` | Removed SQLite from architecture diagram, data model section, tech stack, and notes — replaced with MongoDB-only. 5 edits total. |

### Disk Cleanup

Removed from local disk (all gitignored, none tracked):
- `.DS_Store` files (4 files, ~38 KB)
- `__pycache__/` directories (3 dirs, ~3.3 MB)
- `frontend/tsconfig.tsbuildinfo` (188 KB)
- `backend/.cache/` (36 KB)
- `backend/data/mcp_shield_events.db` (20 KB)
- Stale npm debug log (0 bytes)
