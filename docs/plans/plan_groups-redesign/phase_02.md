# Phase 2 — Frontend: groups table + group detail page

> **Intent:** Turn `/groups` into a searchable table (name, receiver count,
> edit/delete/`Apri`) and add `/groups/:id` with a receiver table (name link,
> truncated slug, copy button) plus the add-receiver form moved off the list page.
> **Shippable alone?** yes — requires Phase 1 backend field `receiver_count`.
> **Preconditions:** Phase 1 DONE.

Follow the repo's existing frontend conventions: pages in `frontend/src/pages/`,
components in `frontend/src/components/`, API client + types in
`frontend/src/api/`, MSW fixtures in `frontend/src/api/mocks/handlers.ts`, tests
co-located in `frontend/src/pages/__tests__/` and
`frontend/src/components/__tests__/`. No new top-level directories: `pages/` and
`components/` already serve these purposes.

---

## Sub-phases

### 2.1 Frontend types, MSW fixtures, and slug CSS
- **Model:** agent-3:haiku
- **Assignment:** agent-3:haiku — mechanical edits.
- **Files:**
  - `frontend/src/api/types.ts:65-69` — `GroupOut`
  - `frontend/src/api/mocks/handlers.ts:32-35` — `fixtureGroups`; `:410-449` — handlers
  - `frontend/src/styles.css` — append at end of file
- **Change:**
  1. `types.ts` — add `receiver_count: number;` to `GroupOut` (after `description`).
  2. `handlers.ts` — add `receiver_count` to both entries of `fixtureGroups`:
     `{ id: "g1", name: "Server Produzione", description: "Ambiente di produzione", receiver_count: 1 }`
     and `{ id: "g2", name: "Backup", description: null, receiver_count: 0 }`.
  3. `handlers.ts` — add a fixture after `fixtureGroups` (after line 35):
     ```ts
     export const fixtureGroupDetail = { ...fixtureGroups[0], receiver_count: 1 };
     ```
  4. `handlers.ts` — add a handler directly after the `http.get("/api/v1/groups", ...)` line (line 415):
     ```ts
     http.get("/api/v1/groups/:groupId", () => HttpResponse.json(fixtureGroupDetail)),
     ```
  5. `styles.css` — append (follow existing plain-CSS conventions, no new libs):
     ```css
     .slug-cell {
       display: flex;
       align-items: center;
       gap: 8px;
       max-width: 320px;
     }
     .slug-cell code {
       overflow: hidden;
       text-overflow: ellipsis;
       white-space: nowrap;
     }
     ```
     Reuse `.group-search` for the search input; if that class does not exist in
     `styles.css`, add `.group-search { margin-bottom: 12px; }` (mirror `.toolbar`).
- **Unit tests:** none (no behavior change).
- **e2e tests:** none (no behavior change).
- **Done:** `npm --prefix frontend run build` passes; `fixtureGroupDetail` is exported; both fixtures carry `receiver_count`.

### 2.2 Shared `CopyButton` and `NewReceiverForm` components
- **Model:** agent-2:sonnet
- **Assignment:** agent-2:sonnet — extraction + new components.
- **Files:**
  - new `frontend/src/components/CopyButton.tsx`
  - new `frontend/src/components/NewReceiverForm.tsx`
  - `frontend/src/pages/GroupsPage.tsx:13-59` (NewReceiverForm source), `:4-9` (imports), `:85` (usage)
- **Change:**
  1. Create `CopyButton.tsx` — a default-export component with prop `{ value: string }`.
     Copy the state machine verbatim from `ReceiverDetailPage.tsx:714-718` +
     `:745-747`: `navigator.clipboard.writeText(value)`, `copied` state, button
     label `{copied ? "Copiato!" : "Copia"}`, `type="button"`, `onClick` fires
     `void handleCopy()`.
  2. Create `NewReceiverForm.tsx` — move the `NewReceiverForm` function from
     `GroupsPage.tsx:13-59` into this file byte-for-byte (same imports it needs:
     `useQueryClient`, `useState`, `apiPost`, `ApiError`/`ReceiverOut`/`Severity`
     types, `ErrorBanner`), export it as default. It keeps `queryKey: ["receivers", groupId]`.
  3. `GroupsPage.tsx` — delete the local `NewReceiverForm` definition (lines 13-59),
     add `import NewReceiverForm from "../components/NewReceiverForm";` to the
     import block, and keep `GroupReceivers` using it as before. Net behavior
     identical. Remove the now-unused `ReceiverOut` and `Severity` imports only if
     they become unused elsewhere in the file (they are used by `GroupReceivers`
     and `SEVERITIES`; remove `SEVERITIES` and the `Severity` import only in 2.4).
- **Unit tests:** `CopyButton` — new `frontend/src/components/__tests__/CopyButton.test.tsx`:
  `clicking writes full value to mocked clipboard and shows Copiato!`.
- **e2e tests:** none (no behavior change; GroupsPage still renders cards).
- **Done:** `npm --prefix frontend run lint` and `run build` pass; GroupsPage renders identically; CopyButton test green.

### 2.3 `GroupDetailPage` + `/groups/:id` route
- **Model:** agent-2:sonnet
- **Assignment:** agent-2:sonnet — implement new page; agent-1:opus review gate (routing).
- **Files:**
  - new `frontend/src/pages/GroupDetailPage.tsx`
  - `frontend/src/App.tsx:44-51` (add sibling route after `/groups`), `:6-17` (imports)
- **Change:**
  1. Create `GroupDetailPage.tsx` as a default-export component:
     - Read `const { id } = useParams<{ id: string }>();` (pattern `ReceiverDetailPage.tsx:688`).
     - Query 1 (group): `useQuery<GroupOut, ApiError>({ queryKey: ["group", id], queryFn: () => apiGet<GroupOut>(`/api/v1/groups/${id}`), enabled: Boolean(id) })`. While `isLoading` render `<p>Caricamento…</p>`; on `error` render `<ErrorBanner error={error} />`.
     - Query 2 (receivers): `useQuery<ReceiverOut[], ApiError>({ queryKey: ["receivers", id], queryFn: () => apiGet<ReceiverOut[]>(`/api/v1/groups/${id}/receivers`), enabled: Boolean(id) })` (pattern `GroupsPage.tsx:63-66`).
     - Header: `<h1>{group?.name ?? "Gruppo"}</h1>`.
     - Table via `DataTable<ReceiverOut>` (import from `../components/DataTable`, reuse `DataTableColumn`). Two columns:
       - `key: "name", header: "Nome receiver", render: (r) => <Link to={`/receivers/${r.id}`}>{r.name}</Link>`
       - `key: "slug", header: "Slug", render: (r) => <div className="slug-cell"><code title={r.slug}>{r.slug}</code><CopyButton value={r.slug} /></div>`
     - Props: `rows={receivers ?? []}`, `rowKey={(r) => r.id}`, `loading={isLoading}` (receivers query), `emptyMessage="Nessun receiver in questo gruppo."`.
     - Error: if receivers query `error`, render `<ErrorBanner error={error} />` above the table.
     - Add-receiver: `const { role } = useSession();` and
       `{hasRole(role, MEMBER_ROLES) && <NewReceiverForm groupId={id ?? ""} />}`
       (pattern `GroupsPage.tsx:85`, roles from `../lib/roles`).
  2. `App.tsx` — import `GroupDetailPage` (alphabetical in the page import block, line 6-17). Insert after the `/groups` route (after line 51):
     ```tsx
     <Route
       path="/groups/:id"
       element={
         <RequireRole allowed={["owner", "admin", "member"]}>
           <GroupDetailPage />
         </RequireRole>
       }
     />
     ```
     React-router v6 longest-match keeps `/groups` working.
- **Unit tests:** none in this sub-phase (covered by 2.5).
- **e2e tests:** none yet (route is reachable only by direct URL; wired in 2.4).
- **Done:** `npm --prefix frontend run build` passes; navigating directly to `/groups/g1` renders the group name and the receiver table against MSW.

### 2.4 `GroupsPage` refactor to searchable table
- **Model:** agent-2:sonnet
- **Assignment:** agent-2:sonnet — implement; agent-1:opus review gate (hot-path page restructure).
- **Files:**
  - `frontend/src/pages/GroupsPage.tsx:217-273` (page body), `:13-88` (remove `NewReceiverForm`, `GroupReceivers`, `SEVERITIES`), `:191-215` (remove `GroupCard`), keep `:90-189` (`EditGroupForm`, `DeleteGroupButton`)
- **Change:** Rewrite `GroupsPage` (lines 217-273) to:
  1. Keep the `["groups"]` query (lines 220-223), `createGroup` (lines 228-238), and the create-group card block (lines 245-264).
  2. Add state: `const [query, setQuery] = useState("");` and `const [editingGroup, setEditingGroup] = useState<GroupOut | null>(null);`.
  3. Compute `const q = query.trim().toLowerCase();` and `filtered` = `(groups ?? [])` filtered on `g.name` and `(g.description ?? "")` (search pattern `GroupList.tsx:12-29`).
  4. Render, in order: `<h1>Gruppi</h1>`, error banner, edit card when `editingGroup` set (reuse `EditGroupForm` + `onDone={() => setEditingGroup(null)}` inside a `div.card`), the create-group card (unchanged), the search input (`<div className="group-search"><input type="search" aria-label="Cerca gruppi" placeholder="Cerca gruppi…" value={query} onChange={...} /></div>`), then a `DataTable<GroupOut>` with columns:
     - `{ key: "name", header: "Nome", render: (g) => <><span>{g.name}</span>{g.description && <span className="card-hint"> — {g.description}</span>}</> }`
     - `{ key: "receiver_count", header: "Receiver configurati", render: (g) => <span>{g.receiver_count}</span> }`
     - `{ key: "actions", header: "Azioni", render: (g) => <div className="row-actions"><Link to={`/groups/${g.id}`}>Apri</Link><button onClick={() => setEditingGroup(g)}>Modifica gruppo</button><DeleteGroupButton group={g} /></div> }`
     - Props: `rows={filtered}`, `rowKey={(g) => g.id}`, `loading={isLoading}`, `emptyMessage={q ? "Nessun gruppo corrisponde alla ricerca." : "Nessun gruppo configurato."}`.
  5. Delete now-unused definitions: `NewReceiverForm` (13-59), `GroupReceivers` (61-88), `GroupCard` (191-215), `SEVERITIES` (line 11). Remove imports that become unused: `ReceiverOut`, `Severity`, `MEMBER_ROLES` (check usage; keep `ADMIN_ROLES`, `hasRole`, `Link`, `useSession`). Ensure `NewReceiverForm` import (from 2.2) is removed only if no longer referenced.
- **Unit tests:** none in this sub-phase (covered by 2.5).
- **e2e tests:** T-GRP2, T-GRP5 (defined in 2.5) — proven there.
- **Done:** `npm --prefix frontend run build` and `run lint` pass; `/groups` renders a table with all rows + `Apri` links to `/groups/:id`; delete flow (`T-UI12`) still works.

### 2.5 Frontend tests for the table and the detail page
- **Model:** agent-2:sonnet
- **Assignment:** agent-2:sonnet — write tests; agent-1:opus review gate (acceptance assertions).
- **Files:**
  - `frontend/src/pages/__tests__/groups.test.tsx` (extend; keep `T-UI12` intact)
  - new `frontend/src/pages/__tests__/groupDetail.test.tsx`
  - `frontend/src/pages/__tests__/testUtils.tsx` (renderWithProviders, unchanged)
- **Change:**
1. `groupDetail.test.tsx` must NOT render `GroupDetailPage` bare — `renderWithProviders`
     only wraps a `MemoryRouter` (see `testUtils.tsx:7-15`), and `useParams` reads the
     matched-route context only when inside a `<Route>`. Without a matching route,
     `id` is undefined and both queries (`enabled: Boolean(id)`) never fire, leaving
     the page loading forever. Mirror the wrapper used by `receiverDetail.test.tsx:16-23`:
     ```tsx
     function renderGroupDetail(initialEntries = ["/groups/g1"]) {
       return renderWithProviders(
         <Routes>
           <Route path="/groups/:id" element={<GroupDetailPage />} />
           <Route path="/receivers/:id" element={<ReceiverDetailPage />} />
         </Routes>,
         initialEntries,
       );
     }
     ```
     Include the `/receivers/:id` route so the receiver-name link resolves when clicked.
     Mock the clipboard before each test:
     ```ts
     const writeText = vi.fn().mockResolvedValue(undefined);
     Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
     ```
  2. Tests:
     - T-GRP2 (groups.test.tsx): render `<GroupsPage />` directly (it uses no `useParams`); assert rows show "Server Produzione" and "1" (receiver_count); type "Backup" in `screen.getByLabelText("Cerca gruppi")`; assert "Server Produzione" row is gone and "Backup" remains; assert the "Apri" link for "Backup" has `href="/groups/g2"`.
     - T-GRP3 (groupDetail.test.tsx): use `renderGroupDetail()`; assert `getByRole("link", { name: "Backup notturno" })` has `href="/receivers/r1"`; assert the slug text is present inside a `code[title]` whose `title` equals the full fixture slug; click the row "Copia" button; assert `writeText` was called with the FULL slug and the button shows "Copiato!".
     - T-GRP4 (groupDetail.test.tsx): use `renderGroupDetail()`; click the receiver name link; `waitFor` the ReceiverDetailPage heading (the receiver name heading, per `receiverDetail.test.tsx` conventions) to confirm navigation to `/receivers/r1`.
     - T-GRP5 (routing): render `renderWithProviders(<App />, ["/groups/g1"])`; assert the detail page renders (e.g. group name heading). Then `renderWithProviders(<App />, ["/groups"])`; assert the list heading "Gruppi" appears (longest-match regression guard). `<App />` mounts its own `Routes`, so no wrapper is needed here.
  3. Keep `T-UI12` as-is; it must still pass (delete buttons now live in table rows).
- **Unit tests:** T-GRP3 (copy writes full slug), T-GRP4 (navigation to receiver detail).
- **e2e tests:** T-GRP2 (search filters table), T-GRP5 (route precedence).
- **Done:** `npm --prefix frontend run test -- --run` green including `T-UI12`, T-GRP2, T-GRP3, T-GRP4, T-GRP5; `npm --prefix frontend run lint` passes.

---

## Phase gates

- **Lint:** `npm --prefix frontend run lint`
- **Build/typecheck:** `npm --prefix frontend run build`
- **Test subset:** `npm --prefix frontend run test -- --run`
- **Regression guard:** T-UI12 (delete group impact dialog) must still pass; Phase 1 backend gates stay green (`make gates`).

## Phase done criterion

On `/groups`: a search input filters the group table; each row shows name,
receiver count, `Apri` (link to `/groups/:id`), `Modifica gruppo`, `Elimina
gruppo`; create/edit/delete still work. On `/groups/:id`: receiver table shows
name (link to `/receivers/:id`) and slug truncated by CSS with a copy button
that writes the full slug and shows "Copiato!"; the add-receiver form is present
for member/admin/owner. All frontend tests and gates pass, including T-UI12.
