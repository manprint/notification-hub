# Architecture Research

**Domain:** Brownfield multi-tenant notification operations dashboard
**Researched:** 2026-08-04
**Confidence:** HIGH

## Standard Architecture

The change crosses the persistence, API, and SPA layers but does not require a new service. Notification state flows from PostgreSQL through tenant-scoped FastAPI schemas and query predicates to React Query data, while receiver preview input should use the same backend cron/time-zone logic as surveillance.

## Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Notification model/migration | Store independent verified state | SQLAlchemy column, Alembic migration, index if justified |
| Notification API | Mutate state with role checks and filter list/detail queries | Extend patch schema, list query, response schemas |
| Notification page/detail | Render and toggle badges, preserve filters | React Query invalidation and existing StatusPill |
| Receiver API/service | Validate unsaved cron and calculate next three times | Shared `croniter` + `zoneinfo` service or preview endpoint |
| Receiver editor | Display live errors and next-run preview | Controlled form state, only save valid schedules |

## Data Flow

1. User clicks a notification badge; API validates tenant and role, updates only the requested state dimension, then the UI invalidates notification queries.
2. User selects read/verified filters; URL search params become API query params and are applied server-side before pagination.
3. User edits cron or time zone; valid input is sent to a preview calculation, which returns the next three occurrences; invalid input returns a structured validation error and disables save.

## Architectural Patterns

### Independent State Dimensions

Use separate `status` and `verified` fields and separate patch operations. This prevents a read transition from changing verification and lets filters combine both predicates.

### Server-Authoritative Schedule Preview

Use the backend's existing five-field validation, IANA time-zone validation, and DST-aware iteration. The browser renders returned timestamps rather than implementing a second cron engine.

### Query-Key Invalidation

After a mutation, invalidate notification list/detail/stat queries as appropriate so counts, badges, and filtered views remain coherent.

## Integration Points

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Frontend ↔ notification API | REST JSON | Preserve existing aliases and pagination |
| Frontend ↔ receiver preview API | REST JSON | Preview must accept unsaved cron/time zone |
| API ↔ PostgreSQL | SQLAlchemy tenant session | RLS and role checks remain mandatory |
| API ↔ croniter/zoneinfo | In-process calculation | Reuse surveillance semantics |

## Anti-Patterns

- Mutating read and verification together: violates independent state semantics.
- Filtering only the currently loaded frontend page: breaks pagination and counts.
- Calculating previews from local browser time: ignores receiver IANA zone and DST.

## Sources

- `.planning/codebase/ARCHITECTURE.md` and `.planning/codebase/STACK.md` (HIGH)
- Existing backend notification and surveillance modules plus frontend pages (HIGH)

---
*Architecture research for: brownfield notification dashboard increment*
*Researched: 2026-08-04*
