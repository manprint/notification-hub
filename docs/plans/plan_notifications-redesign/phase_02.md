# Phase 1 — Table visual fixes (severity, status, actions, responsive)

> **Intent:** Fix the three table glitches and make the table resize without
> glitches, using plain CSS. No data or route change; the page keeps its current
> single-table rendering (phase 2 wires the redesign).
> **Shippable alone?** yes — purely presentational; existing tests stay green.
> **Preconditions:** phase_01 DONE

> **Files touched:** `frontend/src/styles.css`, `frontend/src/pages/NotificationsPage.tsx` (one render wrapper), `frontend/src/components/__tests__/SeverityBadge.test.tsx`, `frontend/src/pages/__tests__/notifications.test.tsx`. No backend files. Follow existing CSS conventions (custom properties, plain CSS, no Tailwind).

---

## Sub-phases

### 1.1 Severity badge never wraps
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/styles.css:281-289` (`.severity-badge`), `frontend/src/components/__tests__/SeverityBadge.test.tsx`
- **Change:** In `.severity-badge`, add `white-space: nowrap;`. Because `th/td` sets `overflow-wrap: anywhere` (`styles.css:111`), the badge text ("CRITICAL" etc.) currently wraps inside the narrow severity cell; `nowrap` on the inline-block badge stops that. Do not change the `td` rule (it is needed for the content column).
- **Unit tests:** extend `SeverityBadge.test.tsx` (after existing T-UI5 badge-class test) with `severity_badge_never_wraps` — render `<SeverityBadge severity="critical" />` and assert the rendered label (Italian label `Critica`, see `SeverityBadge.tsx:4-8`; use `getByText("Critica")` or `/critica/i` — NOT `/critical/i`, the DOM shows `Critica`) has computed style `white-space: nowrap` (use `toHaveStyle({ whiteSpace: "nowrap" })`).
- **e2e tests:** none (no behavior change)
- **Done:** new test passes; `npm run lint` green.

### 1.2 Status labels aligned
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/styles.css:307-313` (`.status-pill`), `frontend/src/pages/NotificationsPage.tsx:130-141` (status column), `frontend/src/pages/__tests__/notifications.test.tsx` (T-LIST4 at `:284`)
- **Change:**
  1. In `styles.css`, add `white-space: nowrap;` to `.status-pill`. Add a new rule `.status-cell { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }` placed right after `.status-pill` rules.
  2. In `NotificationsPage.tsx:133-141`, wrap the status column render in `<div className="status-cell">…</div>` and delete the inline `style={{ marginLeft: 6 }}` on the verified pill (`:136`) — the flex `gap` now provides the spacing. Result: both pills are siblings in one nowrap flex container, so the "Verificata/Non verificata" pill always starts at the same offset after the fixed-content status pill, fixing the misalignment.
  3. Update test T-LIST4 (`:284`) to also assert the pills render inside `.status-cell`: `container.querySelector(".status-cell")` is non-null and contains both the `StatusPill` text and `Verificata`/`Non verificata`.
- **Unit tests:** `status_cell_wraps_pills_aligned` — render page with a `verified: true` row; assert a `.status-cell` element exists, contains both `StatusPill` output and `Verificata`, and its computed `white-space` is `nowrap`; repeat assertion for a `verified: false` row showing `Non verificata` in the same container.
- **e2e tests:** T-LIST4 — existing pass criterion (pills visible, correct label per `verified`) must still pass.
- **Done:** T-LIST4 + new test pass; `npm run lint` green.

### 1.3 Action buttons on the same row
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/styles.css:205-210` and `:75-80` (two `.row-actions` blocks; edit the active `:205-210` block), `frontend/src/pages/__tests__/notifications.test.tsx`
- **Change:** `.row-actions` is defined TWICE in `styles.css`: `:75-80` and `:205-210`. Same specificity, so the LATER block (`:205-210`) wins the cascade — editing only `:75-80` produces no visible change. Edit the winning block `:205-210`: change `flex-wrap: wrap` to `flex-wrap: nowrap` and add `white-space: nowrap;`. For consistency, apply the same two changes to the duplicate `:75-80` block (or delete that duplicate if it is confirmed unused by searching the codebase — keep both blocks consistent either way). Add `.row-actions button { white-space: nowrap; }` so the two buttons ("Segna come letta/non letta" and "Segna come verificata/non verificata", `NotificationsPage.tsx:148-153`) never wrap. If the row is too wide for the container, the existing `.table-wrap { overflow-x: auto }` (`styles.css:116-123`) scrolls horizontally — this is the intended no-glitch behavior; do not add fixed widths to `.row-actions`.
- **Unit tests:** `action_buttons_stay_on_same_row` — render page with a row, locate both buttons via `screen.getByRole("button", { name: /segna come letta/i })` and `/segna come verificata/i`, assert their common parent has class `row-actions` and computed `flex-wrap: nowrap` (via `toHaveStyle`); assert both buttons are children of the same `.row-actions` node.
- **e2e tests:** T-LIST1 and T-LIST2 (read/unread toggle, mark-unread PATCH) must still pass — the buttons' labels and click handlers are unchanged.
- **Done:** new test + T-LIST1/T-LIST2 pass; `npm run lint` green.

### 1.4 Responsive/no-glitch finalization
- **Model:** `agent:deepseek`
- **Assignment:** `agent:deepseek` — implementer; self-review.
- **Files:** `frontend/src/styles.css:98-123` (table, `th/td`, `.table-wrap`)
- **Change:** No structural CSS change is required — the mechanism is already in place: `th/td { overflow-wrap: anywhere }` for the content column and `.table-wrap { overflow-x: auto; min-width: 100% }` for horizontal scroll. Verify and document by reading `styles.css:98-123`: confirm `.table-wrap` retains `overflow-x: auto`, that no new `width`/`min-width` is added to individual `th`/`td`, and that phase 1.1–1.3 `nowrap` rules do not conflict with the content column's `overflow-wrap: anywhere`. If any sub-phase introduced a fixed width on a badge/pill cell, remove it (nowrap + scroll must be the only mechanism). This sub-phase may be a no-op if nothing needs changing — state so in the done criterion.
- **Unit tests:** none (no new rule; guarded by T-SEVR5/T-ALIGN2/T-ROW4 style assertions in 1.1–1.3)
- **e2e tests:** `table_wrap_scrolls_horizontally` — render the page and assert the `.table-wrap` element exists and has computed `overflow-x: auto` (invariant guard for I-3).
- **Done:** `table_wrap_scrolls_horizontally` passes; a read-through of `styles.css:98-123` shows the scroll mechanism intact; no fixed cell widths introduced.

---

## Phase gates

- **Fmt/Lint:** `npm run lint`
- **Test subset:** `npx vitest run src/pages/__tests__/notifications.test.tsx src/components/__tests__/SeverityBadge.test.tsx`
- **Regression guard:** T-LIST1, T-LIST2, T-LIST3, T-LIST4 (notifications), T-UI5 (SeverityBadge), full `npm run test`, `npm run build` (`tsc -b && vite build`)

## Phase done criterion

The four new tests (1.1–1.4) pass, all pre-existing notification/badge tests still pass, `npm run lint` and `npm run build` are green. On the rendered page, severity badges are single-line, the verified pill aligns with the status pill across rows, and the two action buttons sit on one line.
