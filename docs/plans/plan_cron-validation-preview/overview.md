# Cron validation + next-executions preview — Plan Overview

> **Status:** planning | **Supervisor authored:** 2026-08-05
> **Folder:** `docs/plans/plan_cron-validation-preview/`
> **Assignment:** single agent `agent:deepseek-v4-flash` (self-reviews)

## Goal

In the receiver edit form (`frontend/src/pages/ReceiverDetailPage.tsx`), when the
attesa mode is "espressione cron": an invalid cron expression must be rejected
inline and must make the save impossible; while typing, the form must show a
live preview of the next 3 executions computed from the cron expression and the
selected timezone. The backend (`app/services/surveillance.py`, croniter) stays
the authoritative validator, but the frontend must mirror its 5-field rule so
invalid expressions are caught before a PATCH is sent.

```
Reference scenario:
1. Receiver edit → Attesa = "espressione cron". Type "99 3 * * *".
   Expected: inline error "non valida"; no preview; clicking "Salva" →
   NO PATCH to /api/v1/receivers/:id (chiamate === 0), role=alert visible.
2. Type "0 3 * * 1-5", Fuso = "Europe/Rome".
   Expected: preview lists 3 next datetimes (interpreted in Europe/Rome);
   "Salva" → PATCH with expected_cron "0 3 * * 1-5", expected_timezone "Europe/Rome".
3. Type "0 3 *" (3 fields).
   Expected: inline "5 campi" error; save blocked. (already covered by existing test)
```

## Design decisions

| # | Decision | Consequence |
|---|----------|-------------|
| **D1** | Add `cron-parser` (~4.9, ships own TS types, browser-safe) as the single frontend cron engine. | One parser feeds both validation and preview; tz-aware preview via `Intl`; no extra timezone dep; semantics close to croniter for 5-field crons. |
| **D2** | Centralize all cron logic in a pure module `src/lib/cron.ts`: `validateCronExpression`, `validateTimezone`, `nextCronExecutions`, `formatExecutionPreview`. | Component stays dumb; logic unit-testable in isolation (matches existing `src/lib/duration.ts` pattern). |
| **D3** | Mirror backend rules exactly: empty → error; >100 chars → error; ≠5 fields → error keeping the literal message "5 campi"; then parser validity. | Frontend/backend messages and accept/reject sets align; existing component test asserting `/5 campi/` keeps passing. |
| **D4** | Save is blocked by submit-time validation (keeps there chain: setFormError + `return`), with a live inline error shown while typing. Salva button is **not** disabled. | The existing test at `receiverDetail.test.tsx:287` clicks "Salva" and expects the alert; disabling the button would break it. Submit-block + inline error satisfies "cannot save". |
| **D5** | Preview is derived state (cron + timezone + `now`) via `useMemo`; 3 entries; localized to the preview timezone via `Intl.DateTimeFormat`. | No extra state to keep in sync; preview appears as soon as both fields are valid. |
| **D6** | `nextCronExecutions` accepts an optional `now` anchor (default `new Date()`) for deterministic unit tests. | Tests pin exact next-run strings without time-dependent flake. |

## Architecture summary

A tiny pure library (`src/lib/cron.ts`) wraps `cron-parser` and `Intl`. In
`EditReceiverForm`, when `expectedMode === "cron"`, the cron and timezone state
feed two derived values: `cronError` (validation message or null) and the 3-item
preview list. `cronError` gates submit (replaces the word-count-only check at
line 232) and renders inline. Timezone/current-value handling in
`timezoneGroups` is untouched (I-CRN2).

## Phases

| Phase | File | Primary assignment | Shippable alone? |
|-------|------|-------|-----------------|
| 0 — Cron lib + dep (additive) | [phase_01.md](phase_01.md) | `agent:deepseek-v4-flash` | yes |
| 1 — Validation wiring in the form | [phase_02.md](phase_02.md) | `agent:deepseek-v4-flash` | yes |
| 2 — Next-3 preview UI | [phase_03.md](phase_03.md) | `agent:deepseek-v4-flash` | yes |

## Reuse map (top candidates)
| Need | Reuse | Location |
|------|-------|----------|
| Cron validity + next runs | `cron-parser` `parseExpression` | dep in `frontend/package.json` |
| Pure-lib + unit-test convention | `duration.ts` + `__tests__/duration.test.ts` | `src/lib/duration.ts`, `src/lib/__tests__/duration.test.ts:1` |
| Backend validation spec to mirror | `validate_cron` | `backend/app/services/surveillance.py:81`, rule tests `backend/tests/unit/test_surveillance.py:148` |
| Timezone list + include-unknown logic | `timezoneGroups`, `knownTimezones`, `browserTimezone`, `DEFAULT_TIMEZONE` | `src/pages/ReceiverDetailPage.tsx:52,63,77,94` |
| Form error rendering | `<p className="error-banner" role="alert">` | `src/pages/ReceiverDetailPage.tsx:525` |
| Cron input + timezone select block | JSX | `src/pages/ReceiverDetailPage.tsx:435-469` |
| Submit cron validation (to replace) | `cron.trim().split(/\s+/)...` | `src/pages/ReceiverDetailPage.tsx:232` |

## Invariants
- **I-CRN1:** A 5-field cron that croniter (backend) accepts is accepted by the
  frontend and vice-versa for rejection; rules live in one place (`src/lib/cron.ts`).
- **I-CRN2:** A saved/custom timezone must never be silently rewritten; the
  selection menu always includes the current value.
- **I-CRN3:** The PATCH payload shape for cron mode is unchanged:
  `expected_cron` trimmed, `expected_timezone` trimmed or `"UTC"` fallback
  (ReceiverDetailPage.tsx:253-255).

## Risk register
| Risk | Mitigation |
|------|-----------|
| cron-parser/croniter semantic divergence (e.g. dow/dom `*|-` combos) | Preview is advisory; backend remains authoritative; validation gates only the same 5-field + valid rules. Strict cross-C library parity out of scope, flagged in phase_03. |
| "Never fires" cron (`0 0 30 2 *`) makes `next()` throw | `nextCronExecutions` catches and returns `[]`; preview renders "nessuna esecuzione trovata". Proven by T-CRON6. |
| Disabling Salva breaks existing test | D4: keep Salva enabled, block submit → annotated loudly in phase_02. |

---

## Model-assignment summary

| Position | Configured name | Responsibility |
|----------|-----------------|----------------|
| agent-1 (single mode) | `deepseek-v4-flash` | All phases: scope, design, implementation-write authority, tests, docs, and final **self-review**. |