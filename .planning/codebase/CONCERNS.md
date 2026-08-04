# Concerns and Technical Debt

**Analysis Date:** 2026-08-04

## Security-Sensitive Areas

- Tenant isolation is a critical invariant spanning `backend/app/db/session.py`, models, migrations, and every API/service query. New tables must receive matching RLS policies, grants, and explicit tenant constraints.
- Webhook URL validation and the allowlist in `backend/app/outbound/sender.py` protect server-side request behavior. Changes must preserve SSRF defenses and smoke-test host configuration.
- JWT/refresh-token rotation, password hashing, invitation tokens, and encrypted channel credentials cross `backend/app/core/security.py`, `backend/app/services/identity.py`, and auth routers; changes need focused security tests.
- `.env` and deployment secret files must never be read into generated documentation or committed with real credentials. The repository includes deployment examples that require operator-generated secrets.

## Operational Fragility

- Delivery correctness depends on the transaction/outbox/after-commit/reconciliation chain across `backend/app/api/ingest.py`, `backend/app/tasks/enqueue.py`, and `backend/app/tasks/delivery.py`.
- Celery periodic jobs and surveillance behavior are distributed across `backend/app/tasks/celery_app.py` and `backend/app/tasks/maintenance.py`; schedule, idempotency, and tenant context changes can affect all tenants.
- MinIO payload storage introduces a database/object-store consistency boundary in `backend/app/services/storage.py`; retention and cleanup must remove both representations safely.
- Compose service health and migration ordering are part of startup correctness. Changes to `docker-compose.yml`, `deploy/api/entrypoint.sh`, or nginx need container smoke verification.

## Complexity Hotspots

- `backend/app/tasks/maintenance.py` contains multiple maintenance jobs and tenant iteration logic, making it a high-risk area for regressions.
- `backend/app/services/severity_presets.py` embeds a substantial catalog of provider-specific matching rules; changes need regression tests for precedence and RE2 compatibility.
- The API resource routers in `backend/app/api/v1/` encode role checks, tenant filtering, and mutation workflows. Prefer extending services and focused helpers over growing individual routers.
- `frontend/src/pages/PresetsPage.tsx` and other large page components combine query, mutation, permissions, and form state; extract shared behavior carefully to avoid UI regressions.

## Verification Gaps to Watch

- The README records strong current coverage and smoke verification, but external Slack/Google Chat services are represented by mocks in repository tests.
- Operational backup/restore, SMTP delivery, and production reverse-proxy/TLS behavior require environment-level verification beyond unit tests.
- Generated artifacts such as `frontend/coverage/`, `frontend/dist/`, and Python `__pycache__` are present in the workspace; avoid using them as source-of-truth inputs.

---
*Concerns analysis: 2026-08-04*
