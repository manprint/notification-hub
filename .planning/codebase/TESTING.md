# Testing

**Analysis Date:** 2026-08-04

## Backend Test Stack

- pytest with pytest-asyncio is configured in `backend/pyproject.toml` with automatic asyncio mode and a session-scoped event loop.
- Tests are organized into `backend/tests/unit/` and `backend/tests/integration/`.
- Unit tests cover services, schemas, models, security, configuration, errors, and task behavior without external services.
- Integration tests cover RLS, migrations, delivery workers, surveillance, maintenance, and outbound behavior using `docker-compose.test.yml`.
- `respx` mocks HTTP clients; `freezegun` controls time-dependent logic; shared fixtures live in `backend/tests/conftest.py` and `conftest_factories.py`.
- Markers are `unit`, `integration`, and `e2e`; use the marker matching dependency requirements.

## Coverage and Quality Gates

- `make test`, `make test-unit`, and `make test-int` are the standard backend commands.
- `make cov` runs branch coverage with a configured `fail_under = 88` threshold.
- `make gates` runs format check, Ruff, mypy, and the complete backend suite.
- README reports the current verified backend suite at 600 tests and 90.4% coverage; treat the command output as authoritative after changes.

## Frontend Test Stack

- Vitest runs in the Vite/JS DOM environment with setup in `frontend/src/setupTests.ts`.
- Testing Library and `user-event` test rendered interactions; MSW handlers in `frontend/src/api/mocks/` intercept API calls.
- Shared page rendering is in `frontend/src/pages/__tests__/testUtils.tsx` with MemoryRouter and QueryClient providers.
- API client tests live in `frontend/src/api/__tests__/`; feature page tests live in `frontend/src/pages/__tests__/`.
- `make fe-test`, `make fe-cov`, `make fe-lint`, and `make fe-build` are the standard checks.

## System Verification

- `scripts/smoke.sh` exercises the containerized production path, including auth, ingestion, dashboard API, encrypted webhook channel setup, and delivery.
- The smoke profile uses `scripts/mock_webhook.py`, avoiding real external webhook calls.
- When changing deployment, routing, ingestion, or outbound behavior, run the full smoke path in addition to focused tests.

---
*Testing analysis: 2026-08-04*
