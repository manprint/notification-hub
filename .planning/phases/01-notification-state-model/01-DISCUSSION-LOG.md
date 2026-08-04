# Phase 1: Notification State Model - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-08-04
**Phase:** 1-Notification State Model
**Areas discussed:** Verification representation, Existing data migration, Index and query compatibility

## Verification representation

| Option | Description | Selected |
|--------|-------------|----------|
| Boolean `is_verified` | `false` = unverified, `true` = verified; same name across layers | ✓ |
| Enum | Explicit `verified` / `unverified` values | |
| Other | User-defined alternative | |

**User's choices:** Boolean; field name `is_verified`; `NOT NULL DEFAULT false`; expose it immediately in list/detail responses.
**Notes:** Verification remains independent from read/unread and is additive for existing clients.

## Existing data migration

| Option | Description | Selected |
|--------|-------------|----------|
| Existing rows false | Historical notifications start unverified | ✓ |
| Existing rows true | Historical notifications start verified | |
| Other | User-defined alternative | |

**User's choices:** Atomic `NOT NULL DEFAULT false` migration; downgrade removes only the column; test schema, existing-row default, upgrade, and downgrade.

## Index and query compatibility

| Option | Description | Selected |
|--------|-------------|----------|
| No new index in Phase 1 | Evaluate with real filters in Phase 3 | ✓ |
| Partial verified index | Add an index for unverified rows now | |
| Full verified index | Add an index for all rows now | |
| Other | User-defined alternative | |

**User's choices:** Keep existing indexes unchanged, always return a concrete boolean, and use an additive non-breaking API field without endpoint versioning.

## the agent's Discretion

- Alembic revision identifier and exact migration syntax.
- Test file organization, following repository conventions.

## Deferred Ideas

- Index optimization is deferred to Phase 3 with the actual combined filter queries.
