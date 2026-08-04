# Architecture

**Analysis Date:** 2026-08-04

## System Shape

NotifyHub is a self-hosted multi-tenant notification system. nginx is the only public entry point. It serves the React SPA and proxies authenticated API traffic plus public ingestion to the FastAPI service.

## Backend Layers

- `backend/app/main.py` creates the FastAPI application, mounts health/metrics endpoints, and includes API routers.
- `backend/app/api/` contains transport concerns: dependency injection, authentication context, ingestion, and versioned resource routers.
- `backend/app/schemas/` defines Pydantic request/response contracts.
- `backend/app/services/` contains domain operations such as ingestion, severity resolution, authorization, quotas, storage, rate limiting, and surveillance.
- `backend/app/models/` contains SQLAlchemy ORM entities and relationships.
- `backend/app/db/` owns engines, tenant session setup, shared types, and persistence boundaries.
- `backend/app/tasks/` contains Celery delivery, enqueue, and scheduled maintenance workflows.
- `backend/app/outbound/` formats and sends Slack/Google Chat payloads.

## Main Data Flows

1. A client posts to `/ingest/{slug}` in `backend/app/api/ingest.py`.
2. The receiver is resolved by slug, request metadata is normalized, rate/idempotency/quota checks run, and severity rules are evaluated.
3. The notification and delivery outbox rows are committed in one tenant-scoped transaction.
4. An after-commit enqueue schedules Celery delivery; reconciliation handles missed broker messages.
5. The worker decrypts channel credentials, sends the webhook, and updates delivery state with retry/backoff.
6. Authenticated SPA requests use JWT claims and tenant-scoped sessions to access resource routers.

## Isolation and Security Boundaries

- Every tenant-owned query is constrained by both application tenant identifiers and PostgreSQL RLS.
- The default RLS behavior is deny when `app.tenant_id` is absent.
- Database roles separate migration/owner, application, auth, and ingestion responsibilities.
- User-supplied regular expressions use RE2; large bodies are moved to MinIO rather than held inline.

## Entry Points

- API: `backend/app/main.py` and `backend/app/__main__.py`.
- CLI: `backend/app/cli.py`.
- Worker: `backend/app/tasks/celery_app.py`.
- Frontend: `frontend/src/main.tsx` and `frontend/src/App.tsx`.
- Deployment: `docker-compose.yml`, `deploy/api/entrypoint.sh`, and `deploy/nginx/nginx.conf`.

---
*Architecture analysis: 2026-08-04*
