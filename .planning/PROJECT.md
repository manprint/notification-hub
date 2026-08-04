# NotifyHub

## What This Is

NotifyHub is a self-hosted, multi-tenant notification aggregator for teams that need to receive operational messages, inspect them in a web dashboard, and forward selected severities to Slack or Google Chat. Notifications arrive through receiver-specific HTTP endpoints, remain isolated per tenant, and can be monitored for missing scheduled jobs.

## Core Value

Operators must be able to trust that every important operational notification is isolated, visible, actionable, and traceable from ingestion through delivery and verification.

## Business Context

- **Customer**: Teams operating scheduled jobs and infrastructure who need a self-hosted notification hub.
- **Revenue model**: Not defined; current product is self-hosted and deployment-oriented.
- **Success metric**: Operators can reliably identify, filter, acknowledge, and verify notification state without losing delivery or tenant isolation guarantees.

## Requirements

### Validated

- ✓ Multi-tenant notification ingestion through receiver-specific HTTP endpoints — existing
- ✓ Tenant isolation enforced through PostgreSQL Row Level Security and application scoping — existing
- ✓ JWT authentication, rotating refresh tokens, invitations, role permissions, and last-owner protection — existing
- ✓ Group, receiver, channel, and severity-rule management — existing
- ✓ Severity resolution with explicit headers, RE2 rules, receiver defaults, and payload normalization — existing
- ✓ Slack and Google Chat forwarding through an asynchronous outbox and Celery worker — existing
- ✓ Missing-job surveillance using fixed intervals or five-field cron expressions with time zones — existing
- ✓ React dashboard, Docker Compose deployment, operational jobs, health checks, metrics, and smoke verification — existing

### Active

- [ ] Notification read state can be toggled in both directions from the notification list and detail views, subject to existing notification permissions.
- [ ] Notifications have an independent verified/unverified state, represented and toggled in the same direct-action style as read/unread.
- [ ] Notification list filters can independently filter by read/unread and verified/unverified state, while preserving existing filters and counts.
- [ ] Receiver cron expressions are validated as the user edits them; invalid expressions are visibly marked in red, explain the error, and block saving.
- [ ] For every valid receiver cron expression, the receiver editor shows the next three scheduled executions using the currently selected time zone and refreshes after each valid change.
- [ ] Backend and frontend tests cover persistence, authorization, filtering, state transitions, cron validation, time-zone-aware next-run calculation, and invalid-save behavior.

### Out of Scope

- New notification ingestion channels or outbound providers — unrelated to the requested notification-state and receiver-editor improvements.
- Native mobile or push notifications — not needed for this dashboard increment.
- Interactive actions embedded in Slack or Google Chat messages — no requirement for this scope.
- Replacing the existing five-field crontab syntax or changing missing-job surveillance semantics — the task extends its feedback in the editor without changing the scheduling contract.
- Marking notifications verified automatically from delivery success — verification is an explicit operator state and remains independent from read state.

## Context

The codebase is a mature brownfield NotifyHub implementation. The backend is FastAPI with SQLAlchemy/Alembic, PostgreSQL 16, Celery/Redis, and MinIO; the frontend is a React/TypeScript/Vite SPA using React Query, Testing Library, Vitest, MSW, ESLint, and TypeScript checks. nginx is the public entry point and Docker Compose runs the complete stack.

The codebase map in `.planning/codebase/` is complete. Existing code already models notification read/unread state, notification filters, receiver cron configuration, server-side cron validation with `croniter`, and time-zone-aware surveillance calculations. The requested work should extend those established contracts consistently across database, API schemas/routes, frontend state, filters, badges, mocks, and tests.

## Constraints

- **Compatibility**: Preserve the existing API and five-field crontab contract where possible — existing receivers and clients must continue to work.
- **Authorization**: Only `member`, `admin`, and `owner` may change notification verification state — viewers may read but not mutate it.
- **State model**: Read/unread and verified/unverified are independent dimensions — either state must be reversible without changing the other.
- **Time zones**: Next-run previews must use the receiver's selected IANA time zone — UTC is the existing fallback when no explicit zone is configured.
- **Security**: Keep tenant isolation and existing role checks intact — notification state changes must never cross tenant boundaries.
- **Quality**: Changes must pass the established backend and frontend test/lint/type/build gates — this project already maintains broad automated coverage.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Verification is independent from read state | Operators may inspect a notification without completing its operational verification, or verify it before reading it | — Pending |
| State changes use direct clickable badges | Matches the existing read/unread interaction and keeps operator workflow fast | — Pending |
| Cron feedback is live and time-zone aware | Operators need immediate confidence that a scheduled-job policy is valid and will run when expected | — Pending |
| Invalid cron blocks receiver save | Persisting an invalid schedule would make missing-job surveillance unreliable | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-04 after initialization*
