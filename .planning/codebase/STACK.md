# Technology Stack

**Analysis Date:** 2026-08-04

## Languages and Runtime

- Python 3.12 for the backend, Celery workers, migrations, CLI, and operational tooling.
- TypeScript 5.5 and React 18 for the dashboard in `frontend/`.
- Bash for deployment wrappers and smoke tests in `scripts/` and `deploy/`.
- PostgreSQL SQL for migrations, roles, grants, and Row Level Security policies.

## Frameworks and Tools

- FastAPI 0.115 with Uvicorn/Gunicorn serves the API from `backend/app/main.py`.
- SQLAlchemy 2 async sessions and Alembic manage persistence and migrations.
- Celery 5.4 runs delivery and maintenance tasks with Redis as broker.
- React Router and TanStack React Query provide SPA routing and server-state caching.
- Vite builds the frontend; nginx serves the production SPA and proxies API/ingestion.
- pytest, pytest-asyncio, pytest-cov, Ruff, and mypy form the Python quality toolchain.
- Vitest, Testing Library, MSW, ESLint, and TypeScript build checks cover the frontend.

## Key Dependencies

- `asyncpg` and `psycopg` support async application and synchronous maintenance DB access.
- `argon2-cffi`, `PyJWT`, and `cryptography` implement password and token security.
- `redis` provides rate limiting, idempotency, counters, and Celery transport.
- `boto3`/`aioboto3` integrate MinIO/S3 for payloads larger than the inline threshold.
- `google-re2` evaluates user regex rules with linear-time matching.
- `httpx` sends outbound Slack and Google Chat webhook requests.
- `prometheus-client` exposes metrics; `structlog` provides structured logs.

## Configuration and Platform

- Runtime configuration is loaded from `.env` through `pydantic-settings`; `.env.example` is the setup template.
- `docker-compose.yml` defines PostgreSQL 16, Redis 7, MinIO, migration, API, worker, beat, and nginx services.
- `docker-compose.test.yml` provides isolated test dependencies and ephemeral volumes.
- `Makefile` is the canonical interface for install, run, formatting, linting, tests, coverage, and deployment.
- Development requires Docker Compose v2, GNU Make, Python 3.12, and Node.js 22.

---
*Stack analysis: 2026-08-04*
