# Groups Redesign — Plan Overview

> **Status:** planning | **Supervisor authored:** 2026-08-05
> **Folder:** `docs/plans/plan_groups-redesign/`

## Goal

Rework the `/groups` page from card + inline-receiver layout into a searchable
table (name, receiver count, edit/delete/`Apri` actions) and add a new
`/groups/:id` detail page showing the group's receivers in a table (name link,
slug truncated with ellipsis, copy-to-clipboard button) plus the existing
add-receiver form, moved off the list page. Zero regressions to group
create/edit/delete and to `/receivers/:id`.

```
Reference scenario (acceptance, owner role):
1. GET /groups → a search input filters rows; each row shows "Server Produzione",
   receiver count (1), buttons "Modifica gruppo", "Elimina gruppo", "Apri".
2. Click "Apri" on "Server Produzione" → URL /groups/g1 → header shows group
   name; table shows receiver "Backup notturno" (a link) and its slug
   "maritime-backup-notturno-Kj8mQ2xN7vB4pR9wLs3tYc" rendered truncated with "…";
   the row copy button writes the FULL slug to the clipboard and shows "Copiato!".
3. Click "Backup notturno" → URL /receivers/r1 → ReceiverDetailPage renders as today.
4. Add-receiver form is reachable from /groups/g1 (moved from /groups).
```

## Design decisions

| # | Decision | Consequence |
|---|----------|-------------|
| **D1** | Add `receiver_count: int` to `GroupOut`; backend populates it (aggregate count in list, per-group count in get/update, `0` on create). | Backend schema + endpoints change; `frontend/src/api/types.ts` `GroupOut` gains field; existing unit test `test_group_out_schema` must add the field. |
| **D2** | Groups search is client-side local state (reuse `GroupList.tsx` query-filter pattern), not a server query param. | No API change; filter runs on the already-fetched `["groups"]` list. |
| **D3** | New detail route `/groups/:id`, sibling of `/groups`; `Apri` is a react-router `<Link>` (not `useNavigate`). | Route added in `App.tsx`; react-router longest-match keeps `/groups` working. |
| **D4** | Add-receiver form (`NewReceiverForm`) moves off `GroupsPage` to `GroupDetailPage`. | `GroupsPage` becomes table-only; receiver management lives on the detail page. |
| **D5** | Reuse `DataTable` for both the group table and the receiver table. | Consistent `table-wrap` styling; row content supplied via column `render`. |
| **D6** | Slug truncation is display-only CSS (`text-overflow: ellipsis`) + `title` attr; copy uses a new shared `CopyButton` (pattern from `ReceiverDetailPage.tsx:714`). | Full slug preserved in data and clipboard; no JS string slicing. |
| **D7** | Backend test env: extend MSW fixtures/handlers (add `receiver_count` to `fixtureGroups`, add `GET /api/v1/groups/:groupId` handler). | Frontend tests run against complete mock API. |

## Architecture summary

Backend adds one additive field to the group output contract (Phase 1).
Frontend reuses existing primitives: `DataTable`, `ConfirmDialog`,
`EditGroupForm`, `DeleteGroupButton`, the `GroupList` search pattern, and the
`ReceiverDetailPage` copy pattern via a new `CopyButton` (Phase 2). Data flow:
`/groups` table reads `["groups"]` query; `/groups/:id` reads
`["group", id]` + `["receivers", id]`. No new backend endpoint needed
(`GET /groups/{id}/receivers` exists).

## Phases

| Phase | File | Primary assignment | Shippable alone? |
|-------|------|-------|-----------------|
| 1 — Backend `receiver_count` | [phase_01.md](phase_01.md) | `agent-2:sonnet` | yes |
| 2 — Frontend groups table + detail page | [phase_02.md](phase_02.md) | `agent-2:sonnet` | yes |

## Reuse map (top candidates)

| Need | Reuse | Location |
|------|-------|----------|
| Group list fetch | `useQuery(["groups"], apiGet("/api/v1/groups"))` | `frontend/src/pages/GroupsPage.tsx:220-223` |
| Group receivers fetch | `useQuery(["receivers", groupId], apiGet(`/api/v1/groups/${groupId}/receivers`))` | `GroupsPage.tsx:63-66` |
| Group create/edit/delete | `createGroup`, `EditGroupForm`, `DeleteGroupButton`, `ConfirmDialog` | `GroupsPage.tsx:90-189, 228-238` |
| Search filter pattern | local `query` + `filter` | `frontend/src/components/GroupList.tsx:12-29` |
| Generic table | `DataTable<T>` (`columns/rows/rowKey/loading/emptyMessage`) | `frontend/src/components/DataTable.tsx:4-19` |
| Copy to clipboard | inline `copySlug` + "Copiato!" state | `ReceiverDetailPage.tsx:714-718` |
| Router param | `useParams<{ id: string }>()` | `ReceiverDetailPage.tsx:688` |
| Receiver detail route | `path="/receivers/:id"` | `frontend/src/App.tsx:52-59` |
| Backend group list | `list_groups` (list[GroupOut]) | `backend/app/api/v1/groups.py:42-58` |
| Backend group detail | `get_group` | `groups.py:80-88` |
| Backend receivers list | `GET /groups/{group_id}/receivers` | `backend/app/api/v1/receivers.py:255-271` |
| Aggregate count pattern | `select(GroupId, func.count()) ... group_by` | `backend/app/api/v1/presets.py:144` |
| Receiver model | `class Receiver` | `backend/app/models/receiver.py:12` |
| MSW fixtures | `fixtureGroups`, `fixtureReceiver`, handlers | `frontend/src/api/mocks/handlers.ts:32,133,410-449` |
| Frontend test harness | `renderWithProviders` + vitest + RTL + userEvent | `frontend/src/pages/__tests__/testUtils.tsx:7-15` |

## Invariants

- **I-1:** The stored slug is never modified; truncation is CSS-only and the copy button always writes the full slug.
- **I-2:** Add-receiver capability is always reachable from the detail page (moved, never deleted).
- **I-3:** `/receivers/:id` receiver detail behavior is unchanged.

## Risk register

| Risk | Mitigation |
|------|-----------|
| Existing backend unit test breaks (missing `receiver_count`) | Phase 1 updates `tests/unit/test_groups.py::test_group_out_schema` explicitly. |
| MSW lacks `GET /api/v1/groups/:groupId` and fixtures lack `receiver_count` | Phase 2 sub-phase adds both before page components are built. |
| `navigator.clipboard` undefined under jsdom | New detail-page tests mock it via `Object.defineProperty`. |
| React-router `/groups/:id` shadows `/groups` | Longest-match in v6; verified by routing e2e test in Phase 2. |

## Assignment summary

| Position | Model | Responsibility |
|----------|-------|----------------|
| agent-1 | Opus | Architect, supervisor, phase approver, review gates |
| agent-2 | Sonnet | Primary implementer (backend + frontend) |
| agent-3 | Haiku | Exploration, fixtures, CSS, mechanical test work |
