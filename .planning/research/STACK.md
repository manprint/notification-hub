# Stack Research

**Domain:** Brownfield notification dashboard increment
**Researched:** 2026-08-04
**Confidence:** HIGH

## Recommended Stack

The existing stack is already the correct integration point: FastAPI/Pydantic for contracts, SQLAlchemy/Alembic/PostgreSQL for durable notification state, and React/TypeScript with React Query for filters and optimistic-ish invalidation. `croniter` and Python `zoneinfo` are already present in the backend and should remain the source of truth for five-field cron validation and next-run calculation.

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI + Pydantic | existing | API validation and role-aware mutation endpoints | Matches current resource contracts and error handling |
| SQLAlchemy + Alembic | existing | Notification verified state and indexes/migration | Keeps durable state and tenant scoping consistent |
| React + TypeScript | existing | badges, filters, cron preview | Reuses current dashboard patterns and type contracts |
| croniter | 6.x existing | Validate cron and calculate next occurrences | Already used by surveillance and handles the existing five-field contract |
| zoneinfo | Python 3.12 | IANA time-zone conversion | Standard-library, DST-aware, and aligned with receiver configuration |

## Guidance

- Reuse the backend's existing `validate_cron`, `validate_timezone`, and surveillance calculation semantics rather than duplicating a browser parser.
- Return preview data from the API only if the existing receiver contract can be extended cleanly; otherwise calculate it in the receiver editor through a dedicated preview endpoint so unsaved input can be checked without persisting it.
- Keep read and verified as separate fields and query predicates; do not encode four combinations into one enum.
- Add a partial/index strategy for verified filtering only if query plans or expected volume justify it; preserve the existing tenant/status indexes.

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Browser-only cron parser as authority | Can diverge from backend croniter and time-zone rules | Backend validation/calculation contract |
| Combined notification state enum | Makes independent transitions and filters error-prone | Separate read and verified columns |
| Reusing delivery status for verification | Delivery success is not operator verification | Dedicated notification verification state |

## Sources

- Repository `backend/requirements.txt`, `backend/app/services/surveillance.py`, and `frontend/src/pages/ReceiverDetailPage.tsx` — existing implementation patterns (HIGH)
- Repository `.planning/codebase/STACK.md` and `ARCHITECTURE.md` — established architecture (HIGH)

---
*Stack research for: brownfield notification dashboard increment*
*Researched: 2026-08-04*
