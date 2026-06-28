# Testing

## Test Location

All tests are in `backend/tests/`.

## Test Files

| File | Tests | Lines | Coverage Area |
|------|-------|-------|---------------|
| `test_prompt_protection.py` | Full | 400+ | Injection detection, sanitization, edge cases |
| `test_discovery_adapters.py` | Partial | — | Adapter dedup, scraper URL validation |
| `test_manual_job_entry.py` | Partial | — | Fuzzy matching, manual entry validation |
| `test_huggingface_local_provider.py` | Minimal | 30 | HF local provider routing without API key |
| `test_agent_chat.py` | Partial | 53 | Intent classification, job search scoring, error handling |
| `test_ai_daily_budget.py` | Partial | — | Daily budget enforcement |
| `test_csv_import_sanitization.py` | Full | 67 | CSV formula injection, HTML stripping, text sanitization |
| `test_job_generation_specificity.py` | Full | 107 | Job-specific context extraction, tailored resume, interview prep |

## Test Runner

```bash
cd backend
python -m pytest tests/ -v
```

## Coverage Gaps

The following areas have **no tests**:

- API endpoints (no integration/E2E tests)
- Profile management (CRUD, resume upload, AI extraction)
- Gmail ingestion (OAuth flow, email parsing)
- LinkedIn integration (RapidAPI, scrapers)
- Authentication (login, register, password reset, token refresh)
- Automation engine (rules, execution, history)
- Publishing engine (draft, approve, publish)
- Scheduler (job registration, execution)
- Worker queue (enqueue, process, retry)
- Rate limiting (middleware, enforcement)
- Compliance (export, deletion, retention)
- Observability (metrics, alerts)
- Backups (snapshot, prune, S3 upload)
- Teams/RBAC (organizations, workspaces, members, permissions)
- Scoring (heuristic scoring for all opportunity types)
- Resume builder (DOCX rendering, templates)
- Opportunity classifier (classification logic)
- Discovery (public sources, import pipeline)
- Frontend (no JavaScript/React tests at all)

## Mocking Strategy

- `conftest.py` sets up `sys.path` and a `tmpdir` fixture
- `monkeypatch` is used for mocking (e.g., AI provider calls, DB functions)
- No dedicated mock DB or test fixtures for MongoDB
- No test factories or seed data patterns

## Running Specific Tests

```bash
# All tests
python -m pytest tests/

# Specific file
python -m pytest tests/test_prompt_protection.py -v

# Specific function
python -m pytest tests/test_csv_import_sanitization.py::test_neutralize_csv_formula_prefixes_risky_cells -v

# With coverage
python -m pytest tests/ --cov=job_assistant
```
