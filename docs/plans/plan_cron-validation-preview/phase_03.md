# Phase 2 — Next-3 executions preview

> **Intent:** when the attesa mode is "espressione cron", show a live preview of
> the next 3 executions computed from the cron + timezone while the user types.
> **Shippable alone?** yes — additive UI and one derived value.
> **Preconditions:** phases 01 and 02 DONE (validation already blocks bad crons).

## Feature detail
Preview is advisory. Cross-library (cron-parser vs croniter) parity for exotic
day-of-month/day-of-week `|-*` combinations is out of scope: the backend
remains authoritative. If `nextCronExecutions` returns an empty list, render a
"nessuna esecuzione trovata" note instead of dates (I-CRN1, backend line 38-44
notes never-fire crons are legal but empty).

---

## Sub-phases

### 2.1 Compute and render the 3-item preview
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — self-review
- **Files:** `src/pages/ReceiverDetailPage.tsx` — state block near `:173-186`,
  cron fieldset `:435-467`
- **Change:**
 1. Import from `../lib/cron`:
    `nextCronExecutions`, `formatExecutionPreview` (add to the import added in
    phase 1).
 2. Add a derived value (colocated with the `cronError` from phase 1):
    ```ts
    const nextExecutions = (() => {
      if (expectedMode !== "cron" || cronError) return [];
      try {
        return nextCronExecutions(cron.trim(), timezone.trim() || "UTC");
      } catch {
        return [];
      }
    })();
    ```
    Note `cronError` is `null` when the cron is valid, so `nextExecutions` is
    computed only for valid crons. `nextCronExecutions` already never throws
    (phase_01 0.2), the extra `try/catch` is belt-and-suspenders.
 3. Inside the `expectedMode === "cron"` block (`:435-467`), after the timezone
    `<select>` and before the existing `card-hint` (`:468`), render:
    ```tsx
    {nextExecutions.length > 0 ? (
      <ul className="cron-preview" aria-label="Prossime esecuzioni">
        {nextExecutions.map((d) => (
          <li key={d.toISOString()}>{formatExecutionPreview(d, timezone.trim() || "UTC")}</li>
        ))}
      </ul>
    ) : (
      !cronError && expectedMode === "cron" && (
        <p className="card-hint">Nessuna esecuzione trovata per questa espressione cron.</p>
      )
    )}
    ```
 4. Add a small `.cron-preview` rule to `src/styles.css` (follow existing list
    styling; no new file). Content is a compact, monospace-friendly list.
- **Unit tests:** none (pure formatting already covered by T-CRON7).
- **e2e tests:** `T-PRE1`, `T-PRE2` below.
- **Done:** typing a valid cron + timezone renders exactly 3 `<li>` entries
  whose text is localized to the selected timezone; an empty result renders the
  "Nessuna esecuzione trovata" note; the fieldset still shows the hint.

### 2.2 Assert the preview end-to-end
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — acceptance assertions (self-review)
- **Files:** `src/pages/__tests__/receiverDetail.test.tsx` — add to the cron
  describe block next to T-VAL*.
- **Change:** e2e cases (reuse `renderReceiverDetail`, `setRefreshToken`):
  - `T-PRE1` — select `"Attesa"` = `"cron"`, type `0 3 * * 1-5`; assert
    `screen.getAllByLabelText("Prossime esecuzioni")` yields 3 list items; each
    text matches a date/time pattern and no two items share the same string.
  - `T-PRE2` — with the same cron, change `Fuso dell'espressione` to
    `"Europe/Rome"`; assert the first `<li>` text now shows a Rome-based time
    (it differs from the UTC rendering for the same execution — assert
    `toNotEqual`), proving the timezone reaches `Intl.DateTimeFormat`.
- **Unit tests:** none.
- **Done:** `T-PRE1`/`T-PRE2` render; preview reflects timezone changes.

---

## Phase gates

- **Fmt/Lint:** `npm --prefix frontend run lint`
- **Build (type check):** `npm --prefix frontend run build`
- **Test subset:** `npm --prefix frontend run test -- --run src/pages/__tests__/receiverDetail.test.tsx src/lib/__tests__/cron.test.ts`
- **Regression guard:** `T-VAL1..3`, plus the untouched pre-existing receiver
  tests (`:226`, `:287`, `:310`) all still green.

## Phase done criterion
With a valid cron + timezone the form live-shows 3 localized next executions;
with an invalid or never-fire cron it shows the error or the "nessuna
esecuzione" note and never a partial or duplicate preview. `T-PRE1` and
`T-PRE2` pass. Full reference scenario (overview.md §1) is satisfied.