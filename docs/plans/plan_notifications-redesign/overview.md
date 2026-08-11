# Notifications Page Redesign — Plan Overview

> **Status:** planning | **Supervisor authored:** 2026-08-05
> **Folder:** `docs/plans/plan_notifications-redesign/`
> **Assignment:** single-agent mode, `agent:deepseek` for every sub-phase. Final review is an explicit self-review.

## Goal

Rework the notifications page so that the landing view is a list of the configured
groups, and the notifications table (unchanged in behavior) is shown only after
entering one group. Fix three table glitches — severity badge wrapping, misaligned
status labels, action buttons not on the same row — and make the table resize
coherently with no visual glitches. Plan is frontend-only: zero backend changes.

```
Reference scenario: user opens /notifications
  -> sees grid of configured groups (name + description)
  -> clicks "Gruppo A"
  -> URL becomes /notifications?group_id=A
  -> table shows ONLY A's notifications; severity badge single-line;
     "Verificata/Non verificata" pill aligned with the status pill;
     "Segna come letta" and "Segna come verificata" on the same row
  -> narrow window: table scrolls horizontally inside .table-wrap, no wrapping
  -> "Torna ai gruppi" link returns to the group grid
```

## Design decisions

| # | Decision | Consequence |
|---|----------|-------------|
| **D1** | Group context is the query param `group_id` on `/notifications` (`/notifications?group_id=X`). | Reuses the existing `useSearchParams` + filter machinery (`NotificationsPage.tsx:41-48`); no new route, no conflict with `/notifications/:id`; deep-link/refresh-safe. |
| **D2** | Remove the "Tutti i gruppi" aggregated view. `/notifications` without `group_id` renders the group grid. | The existing dropdown option "Tutti i gruppi" (`NotificationsPage.tsx:177`) and test T-UI9 change behavior — called out loudly in phase 2. |
| **D3** | Group switching is back-to-list only; the group dropdown is removed from the toolbar. | Toolbar loses one `<select>` (`NotificationsPage.tsx:165-183`); a "Torna ai gruppi" Link is added above the table. |
| **D4** | Group cards show name + description only, from the existing `GroupOut` (`types.ts:65-69`, `GET /api/v1/groups`). | No backend change; no unread-count badge. |
| **D5** | Table fixes via plain CSS (project has no Tailwind). Badges/pills/buttons get `white-space: nowrap`; status column wrapped in a `.status-cell` flex container; `.row-actions` set to `nowrap`. | `styles.css` edits + one render wrapper. Overflow handled by the existing `.table-wrap { overflow-x: auto }` (`styles.css:116-123`) — the no-glitch mechanism. |
| **D6** | Mutation contracts unchanged: `PATCH /notifications/{id}` with `{status, verified}`, `POST /bulk-read` with `{group_id, severity_min, source, q}`. | `setStatus`/`setVerified`/`bulkRead` (`NotificationsPage.tsx:66-86`) untouched in payload; guard with invariants I-1/I-2. |
| **D7** | `useNotifications` gains an optional `enabled` flag; the page passes `enabled: !!groupId`. | Prevents the aggregated no-group fetch on the grid view (D2). Single caller, default `true` keeps the hook safe. Changes `useNotifications.ts:24-41`. |

## Architecture summary

Single page component (`NotificationsPage`) branches on the `group_id` search param:
no group -> render the new `GroupList` component (group grid, from `GroupOut`);
group set -> render the existing table flow with all existing filters, scoped to
that group, plus a back link. CSS-only fixes to `styles.css` and one status-cell
wrapper. Data flow and API unchanged; `useNotifications` only gains an optional
`enabled` flag (D7).

## Interface (frontend URL surface)

- Route `/notifications` is unchanged; group context is `?group_id=<id>` (D1).
- No new backend endpoint; `GET /api/v1/groups` (grid data) and all notification
  mutations are reused unchanged (I-1, I-2, I-5).

## Protocol / schema

N/A — no wire-protocol or data-structure change. Only existing `GroupOut`
(`types.ts:65-69`) is referenced; no backward-compat concern.

## Phases

| Phase | File | Primary assignment | Shippable alone? |
|-------|------|-------|-----------------|
| 0 — Scaffolding: bulk-read MSW handler + `GroupList` component | [phase_01.md](phase_01.md) | `agent:deepseek` | yes |
| 1 — Table visual fixes (severity/status/actions + responsive) | [phase_02.md](phase_02.md) | `agent:deepseek` | yes |
| 2 — Group-first navigation redesign | [phase_03.md](phase_03.md) | `agent:deepseek` | yes |
| 3 — States, final polish, docs + full regression | [phase_04.md](phase_04.md) | `agent:deepseek` | yes |

## Reuse map (top candidates)

| Need | Reuse | Location |
|------|-------|----------|
| Group data type | `GroupOut` | `frontend/src/api/types.ts:65-69` |
| Groups API call | `apiGet<GroupOut[]>("/api/v1/groups")` | `NotificationsPage.tsx:50-53`, handler `mocks/handlers.ts:415` |
| Notifications fetch | `useNotifications(filters)` — add `enabled` option (D7) | `frontend/src/hooks/useNotifications.ts:24-41` |
| Group fixtures (tests) | `fixtureGroups` | `mocks/handlers.ts:32-35` |
| Table render | `DataTable` | `frontend/src/components/DataTable.tsx:23-67` |
| Empty/loading placeholder | `EmptyState` | `frontend/src/components/EmptyState.tsx` |
| Error banner | `ErrorBanner` | `frontend/src/components/ErrorBanner.tsx` |
| Badge + pill | `SeverityBadge`, `StatusPill` | `SeverityBadge.tsx:11-12`, `StatusPill.tsx:13-14` |
| Table/table-wrap CSS | `.table-wrap`, `th/td` | `styles.css:98-123` |
| Badge/pill CSS | `.severity-badge`, `.status-pill` | `styles.css:281-313` |
| MSW server wiring | `setupServer(...handlers)` | `mocks/server.ts`, `setupTests.ts:3-7` |
| Notification page tests | T-UI9, T-LIST1-4, bulk-read | `pages/__tests__/notifications.test.tsx` |

## Invariants

- **I-1:** Read/verified mutations keep hitting `PATCH /api/v1/notifications/{id}` with `{status, verified}` — payload unchanged (guards: T-LIST2, T-LIST3).
- **I-2:** `bulk-read` still posts `{group_id, severity_min, source, q}` (guard: bulk-read request test).
- **I-3:** Every badge, pill and row-action button renders on a single line at default and narrow widths.
- **I-4:** Group context is fully URL-driven (`group_id`); refresh/deep-link preserves the selected group.
- **I-5:** No file outside `frontend/src/` is modified; backend gates must stay green.

## Risk register

| Risk | Mitigation |
|------|-----------|
| CSS fixes regress existing table layout | Phase 1 is isolated to `styles.css` + one wrapper; full existing test suite must stay green; T-LIST1..T-LIST4 regression guard. |
| Group-grid redesign breaks filters | Phase 2 keeps all toolbar selects except the group one; T-GRP4 asserts filtering still works group-scoped. |
| Test T-UI9 depends on removed dropdown | Rewritten in phase 2 (2.3) with the group-grid flow; flagged loudly. |
| Missing MSW bulk-read handler hides request bugs | Added in phase 0.1 with client test. |
| Narrow-window glitches | `.table-wrap` horizontal scroll + `nowrap` on badges/pills/buttons (phase 1.4) verified by T-ROW4/T-SEVR5 style assertions. |

## Model-assignment summary

| Position | Model tag | Responsibility |
|----------|-----------|----------------|
| agent-1 (single) | `agent:deepseek` | All phases, architecture, implementation, tests, self-review (final review is self-review). |
