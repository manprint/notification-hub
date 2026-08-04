# Repository Structure

**Analysis Date:** 2026-08-04

## Top-Level Layout

- `backend/` — Python package, migrations, requirements, and backend tests.
- `frontend/` — Vite React/TypeScript application and browser tests.
- `deploy/` — API/frontend images, nginx, PostgreSQL initialization, and all-in-one packaging.
- `scripts/` — operational wrapper and end-to-end smoke utilities.
- `docs/` — operational, review, severity, and implementation-plan material.
- `README.md`, `Makefile`, and Compose files — project entry points and developer commands.

## Backend Placement Rules

- Add HTTP endpoints under `backend/app/api/v1/` and register routers in `backend/app/main.py`.
- Add request/response types under `backend/app/schemas/`; keep persistence entities under `backend/app/models/`.
- Put reusable domain behavior under `backend/app/services/`, not directly in routers.
- Put broker-facing work under `backend/app/tasks/`; keep synchronous outbound protocol code under `backend/app/outbound/`.
- Add schema changes as new Alembic revisions under `backend/alembic/versions/`.
- Add unit tests under `backend/tests/unit/`; integration tests needing Compose dependencies belong under `backend/tests/integration/`.

## Frontend Placement Rules

- Route-level screens belong in `frontend/src/pages/` and are wired in `frontend/src/App.tsx`.
- Shared UI belongs in `frontend/src/components/`; session and query behavior belongs in `frontend/src/hooks/`.
- API transport and shared TypeScript contracts are in `frontend/src/api/`.
- Small pure helpers belong in `frontend/src/lib/`.
- Page tests live beside the page test suite under `frontend/src/pages/__tests__/`; API client tests are under `frontend/src/api/__tests__/`.

## Naming and Boundaries

- Python modules and functions use snake_case; classes and Pydantic/SQLAlchemy types use PascalCase.
- React components/pages use PascalCase filenames and default exports; hooks use `use*` names.
- Keep tenant context explicit in service signatures and database access.
- Preserve the router → service → model/session layering when adding features.

---
*Structure analysis: 2026-08-04*
