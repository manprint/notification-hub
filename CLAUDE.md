# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

NotifyHub: self-hosted, multi-tenant notification aggregator. Receives messages via
`POST /ingest/{slug}`, stores them tenant-isolated (Postgres RLS), shows them in a React
dashboard, forwards to Slack/Google Chat above a configured severity threshold. Full functional
spec, and the single source of truth for behavior, is `notifyhub-spec.md`. Build plan/status is in
`docs/plan_NotifyHub/` (phases 0-10, all DONE) and `docs/REVIEW.md`.

## Commands

Backend (from repo root, Makefile is canonical):

```bash
make install       # backend dev deps (pip)
make up             # start dev stack (docker compose): postgres, redis, minio, migrate, api, worker, beat, nginx
make down
make up-test        # ephemeral test deps: postgres 5433, redis 6380, minio 9002/9003
make down-test
make migrate        # alembic upgrade head, dev stack
make migrate-test   # alembic upgrade head, test stack (ENV_FILE=.env.test)
make test           # pytest -q, full suite
make test-unit      # pytest -m unit
make test-int       # pytest -m integration
make cov            # pytest --cov, branch coverage, fail_under=88
make fmt / fmt-check   # ruff format
make lint           # ruff check
make types          # mypy
make gates          # fmt-check + lint + types + test — run before considering backend work done
```

Single test file/case: `cd backend && pytest tests/unit/path/to/test_x.py::test_name -q`

Frontend:

```bash
npm --prefix frontend install
make fe-lint    # eslint, must be zero warnings
make fe-test    # vitest --run
make fe-cov     # vitest --coverage
make fe-build   # tsc + vite build
```

System-level smoke test (containerized stack, real webhook mock, not `ASGITransport`):

```bash
bash scripts/smoke.sh
```

Run this after changes to deployment, routing, ingestion, or outbound delivery, in addition to
focused tests.

Test stacks use ephemeral volumes; after changing DB roles (`deploy/postgres/initdb/00-roles.sql`)
run `make down-test && make up-test` to pick them up.

## Architecture

```
nginx (public entry, SPA + /api/v1/* + /ingest/*)
  -> api (FastAPI)  -> PostgreSQL 16 (RLS forced)
                     -> MinIO (payloads > 1MB)
  -> worker/beat (Celery, sync) <-> redis (broker, rate limit, idempotency, counters)
```

- `backend/app/api/` — transport layer: DI, auth context, ingestion endpoint, versioned routers
  under `api/v1/`. Register new routers in `backend/app/main.py`.
- `backend/app/schemas/` — Pydantic request/response contracts.
- `backend/app/services/` — domain logic: ingestion, severity resolution (`severity.py`,
  `rule_chain.py`), authz, quotas, storage, rate limiting, surveillance. Put reusable domain
  behavior here, not in routers.
- `backend/app/models/` — SQLAlchemy ORM entities.
- `backend/app/db/` — engines, tenant-scoped session setup, shared types.
- `backend/app/tasks/` — Celery delivery, enqueue, scheduled maintenance (`celery_app.py`).
- `backend/app/outbound/formatters/` — per-provider Slack/Google Chat payload formatting.
- `backend/app/core/` — config (`config.py`, centralized, don't read env vars ad hoc elsewhere),
  errors (`errors.py`), crypto (`crypto.py`).
- Router → service → model/session layering: preserve it when adding features.

Ingestion flow: `POST /ingest/{slug}` (`backend/app/api/ingest.py`) resolves receiver by slug,
normalizes request, runs rate/idempotency/quota checks, evaluates severity chain, commits
notification + outbox `deliveries` row in one tenant-scoped transaction, enqueues Celery delivery
after commit. A 5-minute reconciliation job recovers anything the broker loses. Worker decrypts
channel credentials, sends the webhook, updates delivery state with retry/backoff.

Multi-tenancy/isolation: shared schema, `tenant_id` on every tenant-owned row, Postgres RLS forced
(default-deny without `app.tenant_id` set via `SET LOCAL` per transaction). Four DB roles, none
`BYPASSRLS`. Include tenant_id in queries explicitly even though RLS also enforces it — don't rely
on RLS alone.

Other notable design points:
- User-supplied regexes run through `google-re2` (linear time, no ReDoS).
- Payloads >1MB go to MinIO (`storage_key` column + 4096-char `content_preview` for
  list/search/forwarding).
- `webhook_url` is AES-GCM encrypted at rest, never returned in plaintext by the API.
- Slugs are `group-receiver-token` (22-char token, 128 bits entropy); renaming a receiver does not
  change its slug (use `rotate-slug`, admin+ only).
- Nonexistent slug / disabled receiver / suspended tenant all return uniform 404 (no enumeration
  oracle).

Frontend (`frontend/src/`):
- `pages/` — route-level screens, wired in `App.tsx`.
- `components/` — shared UI.
- `hooks/` — session/query behavior (`use*` names).
- `api/` — transport + shared TS types (`client.ts`, `types.ts`); MSW handlers in `api/mocks/`.
- `lib/` — small pure helpers, including `roles.ts` for `RequireRole`/role checks.
- TanStack Query manages remote state; invalidate relevant query keys after mutations.
- Page tests: `pages/__tests__/` (shared render helpers in `testUtils.tsx`). API client tests:
  `api/__tests__/`.
- No native `<select multiple>` for multi-select UI — use checkbox lists instead.

## Conventions

- Python 3.12, Ruff-formatted, 100-char lines, type hints required (mypy strict-optional,
  `disallow_untyped_defs`).
- Async (`async def`/`AsyncSession`) for FastAPI/API-facing DB paths; sync SQLAlchemy sessions only
  for Celery maintenance tasks.
- Structured errors via `backend/app/core/errors.py`; logging via `structlog` with named fields,
  not ad hoc string logs.
- New backend endpoints go under `backend/app/api/v1/`; new schema changes are new Alembic
  revisions under `backend/alembic/versions/`.
- Backend tests: `unit`/`integration`/`e2e` pytest markers; unit tests have no external deps,
  integration tests need `docker-compose.test.yml` services. `respx` for HTTP mocking, `freezegun`
  for time. Shared fixtures in `backend/tests/conftest.py` / `conftest_factories.py`.
- Python snake_case; classes/Pydantic/SQLAlchemy types PascalCase. React components/pages
  PascalCase filenames with default exports.
- ESLint and `tsc` build must pass with zero warnings on the frontend.
