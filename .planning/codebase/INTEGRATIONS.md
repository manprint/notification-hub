# Integrations

**Analysis Date:** 2026-08-04

## Databases and Storage

- PostgreSQL 16 is the system of record for tenants, users, groups, receivers, notifications, channels, deliveries, rules, and tokens.
- `backend/app/db/session.py` provides async tenant-scoped sessions; `backend/app/db/sync_session.py` supports Celery maintenance work.
- `backend/alembic/versions/` contains the schema history; `deploy/postgres/initdb/00-roles.sql` creates the least-privilege database roles.
- Row Level Security is enabled for tenant-owned tables, with `app.tenant_id` set using `SET LOCAL` per transaction.
- MinIO is used through the S3-compatible API for large notification bodies; `backend/app/services/storage.py` owns object key and payload operations.

## Messaging and Background Work

- Redis is used for rate limits, ingestion idempotency, counters, and as the Celery broker.
- `backend/app/tasks/celery_app.py` configures delivery and periodic maintenance schedules.
- `backend/app/tasks/enqueue.py` queues delivery after commit and reconciles pending outbox rows if the broker loses an enqueue.
- `backend/app/tasks/delivery.py` consumes outbox rows and records retry/failure state.

## External Webhooks

- Slack and Google Chat are supported outbound channel types.
- Webhook URLs are encrypted at rest and masked in API responses; sending is centralized in `backend/app/outbound/sender.py`.
- `NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST` restricts permitted webhook hosts; smoke tests add `mock-webhook` explicitly.
- `scripts/mock_webhook.py` and the Compose smoke profile provide a deterministic external endpoint for delivery verification.

## Client and Operational Interfaces

- The React SPA calls `/api/v1/*` through `frontend/src/api/client.ts` and receives access/refresh JWT pairs.
- `POST /ingest/{slug}` is the public ingestion contract for raw notification bodies and wrapper headers.
- `scripts/notifyhub-run.sh` integrates scheduled shell jobs with ingestion and preserves the wrapped command exit code.
- `/metrics` exposes Prometheus metrics internally; `/readyz` is used by Compose health checks.
- SMTP/email configuration is represented in backend settings and invitation/auth flows; no third-party email SDK is hard-coded.

---
*Integration analysis: 2026-08-04*
