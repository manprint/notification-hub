# Phase 3 — Edge states, final polish, docs, full regression

> **Intent:** Harden the redesigned page's loading/error/empty states, run the
> full reference-scenario acceptance test, update the operations doc, and run
> every gate (frontend + backend) to prove zero regressions.
> **Shippable alone?** yes — completes the feature.
> **Preconditions:** phase_03 DONE

---

## Sub-phases

### 3.1 Loading, error and empty states for the group grid and table
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/pages/NotificationsPage.tsx` (group branch added in 2.1, table branch `:159-249`), `frontend/src/components/GroupList.tsx`, `frontend/src/pages/__tests__/notifications.test.tsx`
- **Change:**
  1. Group grid loading: `GroupList` already renders `EmptyState("Caricamento…")` when `loading` (phase 0.2). The `loading` prop is `groupsLoading` (resolved in phase 2.1 step 3 — do not re-decide). Verify it is passed.
  2. Groups error: already wired in phase 2.1 step 5 as `{groupsError && <ErrorBanner error={groupsError} />}`. Verify it renders the banner without crashing when `groupsError` is set. No additional wiring.
  3. Group with zero notifications: the table branch already renders `DataTable` with `emptyMessage="Nessuna notifica trovata."` (`:247`) — verify it shows when `rows` is empty and `isLoading` is false. No change expected.
  4. Do not add unread-count badges (D4).
- **Unit tests:** none (state behavior verified via e2e overrides)
- **e2e tests:** (each overrides the default MSW handlers with `server.use(...)`)
  - T-EMPTY2 — override `GET /api/v1/notifications` to return `{ notifications: [], next_cursor: null, unread_count: 0 }`; with `group_id=g1` render the table and assert `Nessuna notifica trovata.` is visible.
  - T-ERR1 — override `GET /api/v1/groups` to return a 500; at `/notifications` assert `ErrorBanner` content is visible and the grid shows its empty message (or the banner), not a crash.
- **Done:** T-EMPTY2 and T-ERR1 pass; no console errors from the page in any state; `npm run lint` green.

### 3.2 Full reference-scenario acceptance test
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review. (Acceptance assertions are an `agent-1` review gate; in single-agent mode this is a labelled self-review.)
- **Files:** `frontend/src/pages/__tests__/notifications.test.tsx`
- **Change:** Add T-ACCEPT1 — the full flow, matching the reference scenario in `overview.md`: render `/notifications` → assert group grid → click `Gruppo A` → assert URL `group_id` and group-scoped table (severity badge single-line via `toHaveStyle({ whiteSpace: "nowrap" })`, verified pill inside `.status-cell`, both action buttons inside the same `.row-actions`) → click `Torna ai gruppi` → assert grid again. This is the end-to-end acceptance proof.
- **Unit tests:** none
- **e2e tests:** T-ACCEPT1 — as specified.
- **Done:** T-ACCEPT1 passes; it asserts all three visual fixes (1.1–1.3) inside the new navigation flow.

### 3.3 Documentation update + full gate run
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; final doc read is a self-review gate.
- **Files:** `docs/OPERAZIONI.md` (notifications page section), README only if it documents the notifications page navigation
- **Change:** Follow the existing documentation conventions in `docs/OPERAZIONI.md`. Update the notifications page description: the landing view is now the group grid; notifications for a group are reached via `/notifications?group_id=X`; the "Tutti i gruppi" filter is removed; "Torna ai gruppi" returns to the grid. Update only text that is now inaccurate; do not restructure the file. If the README mentions the "Tutti i gruppi" dropdown, update that sentence too; otherwise leave README untouched (I-5).
- **Unit tests:** none
- **e2e tests:** none
- **Done:** doc updated; then run the full gate set (below) and record results in `resume.md`.

---

## Phase gates

- **Fmt/Lint:** `npm run lint` (frontend)
- **Frontend:** `npm run test`, `npm run build` (`tsc -b && vite build`)
- **Backend (unchanged, zero-regression proof):** `make gates` (per `backend/` Makefile: `ruff check .` + `ruff format --check` + `mypy` + `pytest -q`), run from repo root. If `make gates` is not available, run `cd backend && ruff check . && ruff format --check . && mypy app && pytest -q`.
- **Regression guard:** T-GRP1..T-GRP4, T-LIST1..T-LIST4, T-SEVR5, T-ALIGN2, T-ROW4, T-EMPTY2, T-ERR1, T-ACCEPT1, and the full frontend suite.

## Phase done criterion

T-ACCEPT1 passes end-to-end; docs updated; `npm run lint`, `npm run test`, `npm run build` all green; backend `make gates` green proving zero backend regressions; `resume.md` shows all phases and tests `DONE` and `Next:` set to `—` (complete).
