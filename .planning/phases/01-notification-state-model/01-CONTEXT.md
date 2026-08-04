# Phase 1: Notification State Model - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Add durable, tenant-safe persistence for an independent notification verification state while preserving the existing read/unread state and contracts. This phase covers the database/model and list/detail response exposure needed by later API/UI phases; mutation behavior and filtering remain in their roadmap phases.

</domain>

<decisions>
## Implementation Decisions

### Verification representation

- **D-01:** Represent verification as a boolean field named `is_verified` across database, model, API, and frontend contracts — **Reversibility:** costly — changing the public field name later would touch migrations, schemas, client types, and UI consumers.
- **D-02:** `is_verified` is `NOT NULL DEFAULT false`; every notification is always either verified or unverified, with no null/unclassified state.
- **D-03:** Expose `is_verified` immediately in notification list and detail responses as an additive, non-breaking field. Existing clients that ignore it must continue to work.

### Existing data migration

- **D-04:** All existing notifications are migrated to `is_verified = false`; historical read state must not imply verification.
- **D-05:** Use an atomic PostgreSQL/Alembic migration adding `is_verified` with `NOT NULL DEFAULT false`, allowing PostgreSQL to populate existing rows.
- **D-06:** Downgrade removes only the `is_verified` column and returns the schema to its prior shape.
- **D-07:** Migration coverage must test final schema, default behavior on existing records, and upgrade/downgrade reversibility.

### Index and query compatibility

- **D-08:** Do not add a dedicated `is_verified` index in this phase; evaluate indexing with real filter queries in Phase 3.
- **D-09:** Keep existing notification indexes, including the partial unread index, unchanged.
- **D-10:** Backend responses always contain a concrete boolean; no temporary null or client-side fallback is permitted.

### the agent's Discretion

- Exact Alembic revision identifier and migration naming.
- Whether model/API tests are extended in existing test modules or split into a focused file, following repository conventions.
- Exact SQLAlchemy/PostgreSQL syntax used to express the boolean default, provided the resulting schema and rollback behavior satisfy the decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and scope
- `.planning/PROJECT.md` — project context, constraints, and locked milestone decisions.
- `.planning/REQUIREMENTS.md` — requirement NOTIF-03 and complete requirement traceability.
- `.planning/ROADMAP.md` — Phase 1 goal, boundaries, and success criteria.
- `docs/notifyhub-spec.md` — functional/technical source of truth for notification persistence and tenant isolation.

### Existing implementation patterns
- `.planning/codebase/STACK.md` — established Python, PostgreSQL, Alembic, and test stack.
- `.planning/codebase/ARCHITECTURE.md` — backend boundaries and tenant isolation model.
- `.planning/codebase/INTEGRATIONS.md` — PostgreSQL/RLS and persistence integration details.
- `backend/app/models/notification.py` — current notification model and existing index/constraint patterns.
- `backend/app/schemas/notification.py` — current list/detail response contracts.
- `backend/app/db/types.py` — existing notification enum/database type conventions.
- `backend/alembic/versions/` — existing migration history and downgrade conventions.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Notification` SQLAlchemy model — owns the existing `status` field, tenant/receiver foreign keys, partial unread index, and storage constraints; extend this model without altering `status`.
- `NotificationListItemOut` and `NotificationDetailOut` — existing Pydantic response contracts; add the new field as an additive boolean.
- Alembic revisions under `backend/alembic/versions/` — use the established revision naming, PostgreSQL operations, and downgrade style.

### Established Patterns
- Tenant-owned notifications carry `tenant_id` and are protected by application scoping plus PostgreSQL RLS.
- PostgreSQL enum types are declared centrally in `backend/app/db/types.py`; the new state is deliberately boolean and needs no enum change.
- Existing indexes are explicit in `Notification.__table_args__`; do not change the unread partial index in this phase.
- Backend tests use pytest/async fixtures and model/schema unit coverage; migration tests must follow the existing database test setup.

### Integration Points
- Notification ingestion creates rows through the `Notification` model and must inherit the default without special-case changes.
- GET `/api/v1/notifications` serializes list items through `NotificationListItemOut`.
- GET `/api/v1/notifications/{notification_id}` serializes detail through `NotificationDetailOut`.
- Later Phase 2 mutation and Phase 3 filtering will depend on the persisted field and response contract created here.

</code_context>

<specifics>
## Specific Ideas

- The user explicitly wants verification independent from read state; all four combinations must remain representable.
- The field should be named `is_verified`, always concrete, and visible immediately to API consumers.
- Historical notifications must start as unverified so operators do not inherit an unearned verification claim.

</specifics>

<deferred>
## Deferred Ideas

- Dedicated `is_verified` indexing and query optimization belong to Phase 3, once combined filters and real query predicates exist.
- State mutation authorization and clickable UI actions belong to Phases 2 and 4.

</deferred>

---

*Phase: 1-Notification State Model*
*Context gathered: 2026-08-04*
