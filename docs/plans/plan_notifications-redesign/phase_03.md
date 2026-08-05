# Phase 2 — Group-first navigation redesign

> **Intent:** Make `/notifications` land on the group grid; entering a group
> shows the existing table scoped to that group via `?group_id=X`, with the
> toolbar group dropdown removed and a back-to-list link added.
> **Shippable alone?** yes — page fully usable; phase 3 only adds edge states.
> **Preconditions:** phase_01 DONE (GroupList), phase_02 DONE (table fixes)

> **Behavior change (called out loudly):** the "Tutti i gruppi" dropdown option
> and the aggregated (all-groups) notifications view are removed. Test T-UI9
> (`notifications.test.tsx:40-63`) asserts the old dropdown behavior and MUST be
> rewritten in 2.3. Backend is untouched: `GET /api/v1/groups` and all mutation
> endpoints keep their contracts (I-1, I-2).

---

## Sub-phases

### 2.1 Landing view: group grid when no group selected
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/pages/NotificationsPage.tsx:159-249` (render), `frontend/src/hooks/useNotifications.ts:24-41`, `frontend/src/components/GroupList.tsx` (from phase 0)
- **Change:**
  1. Add `import GroupList from "../components/GroupList";`. Do NOT add a `useNavigate` import; group entry uses `setSearchParams` (see step 4).
  2. **Disable the notifications query when no group is selected.** `useNotifications` is `useInfiniteQuery` with no `enabled` option (`useNotifications.ts:24-41`) — it fires on mount, and with no `group_id` that is the aggregated "Tutti i gruppi" fetch (D2 says remove). Change the hook signature to `useNotifications(filters: NotificationFilters, options?: { enabled?: boolean })` and add `enabled: options?.enabled ?? true` to the `useInfiniteQuery` config (`useNotifications.ts:32-41`). This hook's only caller is `NotificationsPage` (`:56`), so the default `true` keeps any unrelated future caller safe. In the page, change the call at `:56` to `useNotifications({ group_id: groupId, severity_min: severityMin, status, source, q: q || undefined }, { enabled: !!groupId })`. Keep `isLoading`/`error` destructured from this call for the TABLE branch only.
  3. Destructure the groups query's own state at `:50-53`: change it to `const { data: groups, isLoading: groupsLoading, error: groupsError } = useQuery({ ... })`. The grid branch must use `groupsLoading`/`groupsError`, NOT the notifications `isLoading`/`error` (which are false/undefined when the notifications query is disabled).
  4. Add a `selectGroup` handler near the existing handlers (`:66-86`): `function selectGroup(groupId: string) { const next = new URLSearchParams(searchParams); next.set("group_id", groupId); setSearchParams(next); }`. Use `setSearchParams`, preserving any active `q`/`severity_min`/`source` filters across group entry.
  5. Early-return branch: when `groupId` is undefined (no `group_id` in the URL), render ONLY the group grid instead of the table:
     ```
     if (!groupId) {
       return (
         <div>
           <h1>Notifiche</h1>
           {groupsError && <ErrorBanner error={groupsError} />}
           <GroupList groups={groups ?? []} loading={groupsLoading} onSelect={selectGroup} />
         </div>
       );
     }
     ```
     Place this right before the existing `return (` at `:159`. The existing `return` block (table + toolbar) becomes the group-selected branch. In the group-selected table branch, keep the existing `{error && <ErrorBanner error={error} />}` where `error` is the notifications query's error (`:162`).
  6. Do not move the notifications query; its `group_id` filter (`:57`) already scopes it. Because of step 2, when `groupId` is undefined the query is simply disabled and never fetched.
- **Unit tests:** none (covered by e2e T-GRP1/T-GRP2)
- **e2e tests:**
  - T-GRP1 — render page at `/notifications` (no `group_id`): assert the group grid renders (`getByRole("button", { name: /gruppo/i })` from `fixtureGroups`), assert no table row is rendered, and that `GET /api/v1/notifications` was NOT called (assert via an MSW `server.use` spy / fetch interceptor that records calls).
  - T-GRP2 — from T-GRP1 state, click a group card: assert the URL contains `group_id=<id>` and the table renders with that group's notifications (assert `GET /api/v1/notifications` was called with `group_id=<id>`, mirroring how T-UI9 currently inspects query params).
- **Done:** T-GRP1, T-GRP2 pass; `npm run lint` green; existing notifications tests pass except T-UI9 (rewritten in 2.3).

### 2.2 Table branch: back-to-list link, group dropdown removed
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/pages/NotificationsPage.tsx:164-183` (toolbar group `<select>`), `:159-161` (heading area)
- **Change:**
  1. Delete the entire group `<select>` block (`:164-183`) from the toolbar. Keep the severity/source/search selects and the "Segna tutte come lette" button (`:185-233`).
  2. Above the `<h1>Notifiche</h1>` (`:161`), add a back link: `<Link to="/notifications">← Torna ai gruppi</Link>` with `style={{ marginRight: 8, fontSize: 13 }}` (reuse the existing `Link` import at `:3`). This is the only group-switching affordance (D3). Note on semantics: the Link drops the `group_id` (and other URL params) but the free-text `q` is component state (`:42`) and the component does not unmount on same-route navigation, so the search term persists across grid→group→grid cycles — intended.
  3. Optionally show the current group name next to the heading: resolve it from the already-fetched `groups` array via `groups?.find((g) => g.id === groupId)?.name` and render it as a subdued `<span>` next to the title. If added, guard the lookup against `groups` being `undefined`.
- **Unit tests:** none
- **e2e tests:** T-GRP3 — from a group-selected page, click `Torna ai gruppi`: assert URL has no `group_id` and the group grid renders again.
- **Done:** T-GRP3 passes; toolbar contains no group `<select>` (assert `screen.queryByRole("combobox", { name: /gruppo/i })` is null in T-GRP3); `npm run lint` green.

### 2.3 Rewrite filter tests for the group-scoped flow (replaces T-UI9)
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/pages/__tests__/notifications.test.tsx:40-63` (T-UI9)
- **Change:** Replace T-UI9's dropdown assertion with group-scoped filter behavior: with `?group_id=g1` set, assert severity/source filters still appear in the `GET /api/v1/notifications` request together with `group_id`, and that selecting them updates the request query params (reuse the request-param capture technique T-UI9 already uses). The old assertion of the "Tutti i gruppi" option is deleted (option no longer exists — D2).
- **Unit tests:** none
- **e2e tests:** T-GRP4 — with `group_id=g1` in the URL, change the severity select to `critical`; assert the `GET /api/v1/notifications` request carries both `group_id=g1` and `severity_min=critical`.
- **Done:** T-GRP4 passes and replaces T-UI9; full `notifications.test.tsx` suite green.

---

## Phase gates

- **Fmt/Lint:** `npm run lint`
- **Test subset:** `npx vitest run src/pages/__tests__/notifications.test.tsx`
- **Regression guard:** T-LIST1..T-LIST4, T-GRP1..T-GRP4, full `npm run test`, `npm run build`

## Phase done criterion

At `/notifications` the group grid renders and no notifications are fetched; clicking a group navigates to `?group_id=X` and shows only that group's table; the back link returns to the grid; filters still work group-scoped (T-GRP4); toolbar has no group dropdown. All invariants I-1..I-5 hold.
