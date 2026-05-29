# Opportunity Intelligence Frontend

Production Next.js replacement for the Streamlit frontend. FastAPI remains the source of truth for authentication, data models, scoring, provider orchestration, automation, audit, and workspace isolation.

## Local Development

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` and run the FastAPI server from the repository root:

```bash
uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
```

## Architecture

- `src/app`: Next.js App Router route groups for auth and authenticated SaaS surfaces.
- `src/services`: typed Axios API layer for existing `/api/v1` FastAPI contracts.
- `src/features`: feature-owned screens for dashboard, opportunities, AI, automation, integrations, team, analytics, and settings.
- `src/components`: reusable layout, chart, and UI primitives.
- `src/stores`: Zustand session/workspace state.

## Migration Plan

1. Run FastAPI and Next.js locally with `CORS_ORIGINS=http://localhost:3000,http://localhost:3001`.
2. Validate authentication, workspace bootstrap, opportunity listing/detail/scoring/material generation, automation, provider, feedback, audit, and health screens against seeded SQLite data.
3. Keep Streamlit available during parallel acceptance testing, but route new users to Next.js.
4. Deploy the frontend to Vercel with `NEXT_PUBLIC_API_URL` pointing to the Render/Railway/Fly API domain.
5. Deploy FastAPI separately with production `JWT_SECRET_KEY`, `APP_ENCRYPTION_KEY`, `APP_BASE_URL`, and restricted `CORS_ORIGINS`.
6. After verification, remove Streamlit hosting from production compose/process managers while leaving backend APIs unchanged.

## Backend Contract Gaps

The current FastAPI auth contract returns only an access token. The frontend persists it and clears on `401`. True refresh-token rotation, forgot-password, and reset-password flows need backend endpoints before those controls can be enabled.
