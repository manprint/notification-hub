# Phase 0 — Scaffolding: bulk-read MSW handler + GroupList component

> **Intent:** Add test infrastructure (missing bulk-read MSW handler) and the
> reusable `GroupList` component, both purely additive. No route or behavior
> change: the notification page still renders exactly as before.
> **Shippable alone?** yes — nothing is wired, no existing test changes.
> **Preconditions:** none

Follow existing project structure throughout: components live in
`frontend/src/components/`, their tests in `frontend/src/components/__tests__/`,
API mocks in `frontend/src/api/mocks/`. No new directories.

---

## Sub-phases

### 0.1 Add MSW handler for `POST /api/v1/notifications/bulk-read`
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review in single-agent mode.
- **Files:** `frontend/src/api/mocks/handlers.ts` (handlers array at `:410-464`), `frontend/src/api/__tests__/client.test.ts`
- **Change:**
  1. In `handlers.ts`, inside the `handlers` array (after the existing notification handlers around `:426-433`), add a `http.post("/api/v1/notifications/bulk-read", ...)` handler returning `200` with `JSON.stringify({ marked_read: 0 })` and `ctx.status(200)`. The response body MUST be `{ marked_read: 0 }`, not `{ count: ... }`: the backend contract field is `marked_read` (`backend/app/schemas/notification.py:92`) and the existing test already asserts that shape (`notifications.test.tsx:182`). Check the file for whether other handlers use `HttpResponse.json` vs `ctx.json` and mirror the local convention used by the `PATCH /api/v1/notifications/:id` handler (the PATCH handler uses `HttpResponse.json`).
  2. In `client.test.ts`, add a test that `apiPost("/api/v1/notifications/bulk-read", { group_id: "g1" })` resolves with status 200 and that the request body sent equals `{ group_id: "g1" }` (mock the request as the other client tests in this file do; if the file has no request-body-capture helper, use a `fetchMock` or MSW `server.use` interceptor consistent with the existing style — check how the existing tests assert requests).
- **Unit tests:** `bulk_read_posts_body_and_succeeds` — asserts the request URL is `/api/v1/notifications/bulk-read`, method `POST`, body `{ group_id: "g1" }`, and response resolves.
- **e2e tests:** none (no behavior change)
- **Done:** `npm run test` green (new test passes, whole suite still green); `npm run lint` green (`eslint src --max-warnings 0`).

### 0.2 Create `GroupList` component + unit tests
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** new `frontend/src/components/GroupList.tsx`, new `frontend/src/components/__tests__/GroupList.test.tsx`, `frontend/src/styles.css`
- **Change:**
  1. Create `frontend/src/components/GroupList.tsx`. Follow the existing component style (default export, typed props, plain function). Props: `groups: GroupOut[]` and `onSelect: (groupId: string) => void`, and optional `loading?: boolean`. Render:
     - if `loading` -> `<EmptyState message="Caricamento…" />` (import `EmptyState` from `./EmptyState`, same as `DataTable.tsx:34`).
     - if `groups.length === 0` -> `<EmptyState message="Nessun gruppo configurato." />`.
     - else a `<div className="group-grid">` containing one `<button className="group-card" key={g.id} onClick={() => onSelect(g.id)}>` per group. Inside each button render `<span className="group-card-name">{g.name}</span>` and, when `g.description` is non-empty, `<span className="group-card-desc">{g.description}</span>`. Import `GroupOut` as `import type { GroupOut } from "../api/types";`.
  2. In `styles.css`, add the `.group-grid`, `.group-card`, `.group-card-name`, `.group-card-desc` rules near the `.toolbar` block (`:342-348`), following the existing plain-CSS conventions and CSS custom properties (`--space-*`, `--color-*`, `--radius`). Grid: `display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: var(--space-3);`. Card: left-aligned text, full width, `text-align: left`, padding `var(--space-3)`. Name: `font-weight: 600`. Desc: `color: var(--color-text-muted); font-size: 13px;`.
  3. Create `GroupList.test.tsx` mirroring the conventions of `components/__tests__/SeverityBadge.test.tsx` (RTL + jest-dom). Mock nothing (pure component).
- **Unit tests:**
  - `group_list_renders_name_and_description` — render with 2 groups; assert `getByText("Gruppo A")` and description text present.
  - `group_list_fires_onSelect_with_id` — render with 2 groups, click a card, assert `onSelect` called with that group's id exactly once.
  - `group_list_hides_empty_description` — render group with `description: ""`; assert no `.group-card-desc` node for it.
  - `group_list_empty_message` — render with `[]`; assert `Nessun gruppo configurato.` visible.
  - `group_list_loading` — render with `loading` true; assert `Caricamento…` visible.
- **e2e tests:** none (component not wired to any route yet — no behavior change)
- **Done:** `npm run test` and `npm run lint` green; `GroupList` not imported anywhere yet (verify with a search for `GroupList` that the only references are the two new files).

---

## Phase gates

- **Fmt:** `npx eslint src --max-warnings 0` (project has no formatter; eslint is the gate)
- **Lint:** `npm run lint`
- **Test subset:** `npx vitest run src/components/__tests__/GroupList.test.tsx src/api/__tests__/client.test.ts`
- **Regression guard:** full `npm run test` still green (phase must be additive)

## Phase done criterion

`npm run lint` and `npm run test` both green; `GroupList.tsx`, `GroupList.test.tsx` exist and are unused by any route; MSW handler for bulk-read exists and `bulk_read_posts_body_and_succeeds` passes. The `/notifications` page output is byte-identical to before this phase.
