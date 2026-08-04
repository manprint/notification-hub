# Coding Conventions

**Analysis Date:** 2026-08-04

## Python

- Python targets 3.12 with Ruff formatting and a 100-character line length, configured in `backend/pyproject.toml`.
- Ruff checks errors, imports, modern syntax, bugbear, async mistakes, security rules, and print usage.
- Type hints are expected on definitions; mypy runs in strict-optional mode with `disallow_untyped_defs`.
- Async FastAPI/database paths use `async def` and `AsyncSession`; synchronous SQLAlchemy sessions are reserved for Celery maintenance.
- Services receive explicit sessions and tenant IDs. Routers validate transport input and delegate domain behavior.
- Errors use the structured application error types in `backend/app/core/errors.py`; logging uses `structlog` events with named fields.
- Secrets are encrypted/decrypted through `backend/app/core/crypto.py` and should not be returned in API schemas.

## Domain Patterns

- Multi-tenant models carry `tenant_id` and queries include tenant constraints even when RLS also protects the table.
- Notification delivery uses an outbox row plus an after-commit enqueue rather than sending within the request transaction.
- Severity calculation is a chain of explicit sources in `backend/app/services/severity.py` and `rule_chain.py`.
- External webhook payload formatting is separated by provider in `backend/app/outbound/formatters/`.
- Configuration is centralized in `backend/app/core/config.py`; avoid reading environment variables ad hoc in feature modules.

## Frontend

- TypeScript types are centralized in `frontend/src/api/types.ts` and API calls go through `frontend/src/api/client.ts`.
- TanStack Query manages remote data; pages invalidate relevant query keys after mutations.
- Access control is expressed through `RequireRole` and role helpers in `frontend/src/lib/roles.ts`.
- Components use explicit props, React hooks, and shared status/error components rather than duplicated presentation logic.
- ESLint and the TypeScript build are required to pass with no warnings.

---
*Conventions analysis: 2026-08-04*
