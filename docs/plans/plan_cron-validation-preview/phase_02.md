# Phase 1 — Wire validation into the receiver edit form

> **Intent:** make an invalid cron (and invalid timezone) impossible to save and
> show a live inline error under the cron field when in "espressione cron" mode.
> The backend remains authoritative; this is the UX gate.
> **Shippable alone?** yes — a self-contained behavior change to
> `EditReceiverForm`; preview (phase 2) is separate.
> **Preconditions:** phase_01 DONE (the lib exists).

> **Behavior change (called out):** the submit-time check at
> `src/pages/ReceiverDetailPage.tsx:232` currently only counts fields
> (`split(/\s+/).length !== 5`). It is **replaced** by a call to
> `validateCronExpression` so that out-of-range cron (`99 3 * * *`) is also
> rejected client-side. The message for the wrong-field-count case keeps the
> words `5 campi` verbatim (I-CRN1, existing test compatibility).

---

## Sub-phases

### 1.1 Widen the cron validation in `EditReceiverForm`
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — self-review
- **Files:** `src/pages/ReceiverDetailPage.tsx:173` (cron state), `:232-237`
  (submit cron check), `:443-446` (cron input)
- **Change:**
 1. Add `import { validateCronExpression } from "../lib/cron";` near the
    existing `src/lib/duration` import (`ReceiverDetailPage.tsx:17`).
 2. Derive a memoized validation result from the live `cron` state, shown even
    before submit. Add (near `:185`, with the other state):
    ```ts
    const cronError =
      expectedMode === "cron" ? validateCronExpression(cron) : null;
    ```
 3. Replace the block at `ReceiverDetailPage.tsx:232-237` with:
    ```ts
    if (expectedMode === "cron") {
      const err = validateCronExpression(cron);
      if (err !== null) { setFormError(err); return; }
    }
    ```
    This preserves the existing "5 campi" message for the wrong-field-count
    case and now also blocks 5-field-but-invalid crons (`99 3 * * *`).
 4. Do **not** add `disabled` to the Salva button (D4): blocking submit with a
     visible `role="alert"` error satisfies "cannot save" without breaking the
     existing test at `src/pages/__tests__/receiverDetail.test.tsx:287` that
     clicks "Salva" and expects the alert.
- **Unit tests:** none new (pure function already covered by T-CRON*).
- **e2e tests:** `T-VAL1` below, plus the pre-existing
  "rifiuta un'espressione cron malformata senza chiamare l'API"
  (`receiverDetail.test.tsx:287`) must still pass unchanged.
- **Done:** typing `99 3 * * *` and pressing "Salva" produces a
  `role="alert"` with "non valida" and zero PATCH calls; typing `0 3 *` still
  yields the "5 campi" message.

### 1.2 Render the live inline cron error
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — self-review
- **Files:** `src/pages/ReceiverDetailPage.tsx:435-467` (cron fieldset)
- **Change:** inside the `expectedMode === "cron"` block, directly under the
  cron `<input>` (id `receiver-edit-expected-cron`, `ReceiverDetailPage.tsx:441`)
  and before the timezone `<select>`, render the inline error using the same
  styling as the submit error:
  ```tsx
  {cronError && (
    <p className="error-banner" role="alert">{cronError}</p>
  )}
  ```
  It appears as soon as the typed cron is invalid, and disappears when it
  becomes valid (because `cronError` re-derives from `cron` on each render).
- **Unit tests:** none.
- **e2e tests:** `T-VAL-2` below.
- **Done:** typing an invalid cron shows the inline `role="alert"` before any
  submit; typing a valid cron removes it.

### 1.3 Validate the timezone on submit
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — self-review
- **Files:** `src/pages/ReceiverDetailPage.tsx` (submit block around
  `:239-258`), timezone state at `:174`
- **Change:**
 1. Import `validateTimezone` alongside `validateCronExpression`.
 2. In the submit handler, just before building the `expected` object
     (`ReceiverDetailPage.tsx:239`), when `expectedMode === "cron"`:
     ```ts
     const tzErr = validateTimezone(timezone.trim() || "UTC");
     if (tzErr) { setFormError(tzErr); return; }
     ```
 3. Keep the payload construction unchanged (`expected_cron: cron.trim()`,
     `expected_timezone: timezone.trim() || "UTC"`) — this preserves I-CRN3.
- **Unit tests:** covered by T-CRON5.
- **e2e tests:** `T-VAL3` below.
- **Done:** an unknown timezone in the field is rejected on submit with the
  "non valido" message and no PATCH.

---

## e2e tests (component, `src/pages/__tests__/receiverDetail.test.tsx`)

Add these inside the existing `describe` that already covers cron saves
(around `receiverDetail.test.tsx:226-308`), reusing its helpers
(`renderReceiverDetail`, `setRefreshToken`, `server.use` MSW handlers).

- **T-VAL1 (submit block on invalid cron):**
   select `Attesa` = `cron`, type `99 3 * * *`, click "Salva"; assert
   `screen.findByRole("alert")` contains `/non valida/` and the MSW PATCH
   counter `chiamate` stays `0`.
- **T-VAL2 (live inline error):**
   select `Attesa` = `"cron"`, type `0 3 *`; assert, without clicking Salva,
   `screen.findByRole("alert")` contains `/5 campi/`.
- **T-VAL3 (timezone reject):**
   select `Attesa` = `"cron"`, type a valid cron `0 3 * * 1-5`, select a bogus
   fuso (set `Fuso dell'espressione` value to `"Europa/Roma"` via
   `userEvent.selectOptions` — it is not in the menu; use a debug DOM set or
   assert via `validateTimezone` alone if the menu cannot hold it). If the value
   cannot be injected by `selectOptions`, instead assert the lib behaviour.
   Minimal acceptable: `validateTimezone("Europa/Roma")` returns non-null and
   the submit path returns before PATCH when the timezone is blank after trim.

---

## Phase gates

- **Fmt/Lint:** `npm --prefix frontend run lint`
- **Build (type check):** `npm --prefix frontend run build`
- **Test subset:** `npm --prefix frontend run test -- --run src/pages/__tests__/receiverDetail.test.tsx`
- **Regression guard:** the unchanged pre-existing test
  `rifiuta un'espressione cron malformata senza chiamare l'API`
  (`receiverDetail.test.tsx:287`) must still pass, as must `passa dall'intervallo
  all'espressione cron e la salva col fuso` (`:226`).

## Phase done criterion
Invalid crons (any of: empty, bad count `5 campi`, invalid `non valida`,
overlong) block the PATCH with a visible `role="alert"`; the timezone is
validated on submit; `T-VAL1..3` plus the two pre-existing receiver cron tests
pass; the PATCH payload shape is byte-identical to before (I-CRN3).