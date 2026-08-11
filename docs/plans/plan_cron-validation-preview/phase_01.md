# Phase 0 — Cron library and dependency (additive)

> **Intent:** add `cron-parser` and a pure, unit-tested `src/lib/cron.ts` that
> validates cron expressions and computes next executions. No UI change here.
> **Shippable alone?** yes — pure addition: a new dependency and a new library
> module; no existing behavior touched.
> **Preconditions:** none.

---

## Sub-phases

### 0.1 Add `cron-parser` dependency
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — self-review
- **Files:** `frontend/package.json`, `frontend/package-lock.json`
- **Change:**
 1. Run `npm --prefix frontend install cron-parser@^4.9.0`.
 2. Confirm `cron-parser` is listed under `dependencies` in
    `frontend/package.json` (it is a runtime dep, not dev).
 3. `cron-parser` ships its own TypeScript types; if the build reports missing
    types, add a module declaration shim in `frontend/src/vite-env.d.ts`.
- **Unit tests:** none (no new logic).
- **e2e tests:** none (no behavior change).
- **Done:** `frontend/package.json` lists `cron-parser@^4.9` under
  `dependencies` and `npm --prefix frontend run build` still passes.

### 0.2 Create `src/lib/cron.ts` (validation + preview API)
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — self-review
- **Files:** create `src/lib/cron.ts`. Follow the existing pure-lib convention
  in `src/lib/duration.ts` (exported functions, no side effects, comments in
  Italian). `src/lib/` already exists and is the correct home — do not create a
  new directory.
- **Change:** export exactly these, mirroring
  `backend/app/services/surveillance.py:81-99`:
  - Constants `CRON_FIELDS = 5` and `CRON_MAX_CHARS = 100`.
  - `validateCronExpression(expression: string): string | null`. Let
    `candidate = expression.trim()`. In this order:
      - `candidate === ""` → `"L'espressione cron è vuota."`
      - `candidate.length > CRON_MAX_CHARS` →
        `"L'espressione cron supera 100 caratteri."`
      - `candidate.split(/\s+/).length !== CRON_FIELDS` →
        `"L'espressione cron deve avere 5 campi come in crontab: minuto ora giorno mese giorno-settimana."`
        (The component test asserts the regex `/5 campi/`, so those two words
        must appear verbatim.)
      - otherwise validate with the parser (below); catch any thrown `Error`
        and return `"Espressione cron non valida: " + candidate`.
      - else `null` (valid).
      - Parser detail: `const iter = parseExpression(candidate, { currentDate: new Date() }); iter.next();`
        inside a `try/catch`. Both construction and `.next()` can throw for
        invalid expressions; every thrown error maps to the "non valida" message.
  - `validateTimezone(name: string): string | null`. Trim; empty →
    `"Scegli un fuso orario correttamente."`; else in a `try/catch` call
    `new Intl.DateTimeFormat("en-US", { timeZone: name })`; on thrown
    `RangeError` → `"Fuso orario non valido: " + name`; else `null`.
  - `nextCronExecutions(expression: string, timezone: string, now: Date = new Date()): Date[]`.
    Build `const iter = parseExpression(expression, { currentDate: now, tz: timezone })`
    inside a `try/catch` (on construction error return `[]`). Then call
    `iter.next()` up to 3 times, collecting `iter.next().toDate()`. Guard each
    `.next()` call: if a `.next()` throws (a never-firing cron such as
    `0 0 30 2 *`), stop and return the dates collected so far. Never let a
    thrown error escape this function.
  - `formatExecutionPreview(date: Date, timezone: string): string` → return
    `new Intl.DateTimeFormat("it-IT", { timeZone: timezone, weekday: "short", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(date)`.
- **Unit tests:** defined in sub-phase 0.3.
- **e2e tests:** none (no UI path).
- **Done:** all four functions are imported from `src/lib/cron` in a throwaway
  probe without TS/build errors; `.next()` never propagates an exception;
  returns match the signatures above.

### 0.3 Unit-test `src/lib/cron.ts` — T-CRON*
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — acceptance assertions (self-review)
- **Files:** create `src/lib/__tests__/cron.test.ts` (new file). Follow
  `src/lib/__tests__/duration.test.ts` structure: `import { describe, expect, it } from "vitest";`.
- **Change:** give the tests and assertions:
  - `T-CRON1 accepts valid 5-field crons` — `it.each(["0 3 * * 1-5", "*/5 * * * *", "0 0 * * 1"])`
    with `expect(validateCronExpression(expr)).toBeNull()`.
  - `T-CRON2 rejects empty and wrong field count` — `it.each(["", "   ", "0 3 * *", "0 3 * * * *", "@daily"])`;
    expect a non-null string; for `0 3 * *` and `0 3 * * * *` the message
    contains `5 campi`; for `""` it contains `vuota`.
  - `T-CRON3 rejects out-of-range / unparsable` — `it.each(["99 3 * * *", "non un cron", "0 3 * * * ; rm -rf /"])`;
    expect non-null message containing `non valida`.
  - `T-CRON4 rejects over-long` — `validateCronExpression("0 " + "3".repeat(200) + " * * *")`
    returns message containing `100 caratteri`.
  - `T-CRON5 timezone validation` — `it.each(["UTC","Europe/Rome","America/New_York"])`
    expect `validateTimezone(...) === null`; `it.each(["", "  ", "Europa/Roma"])`
    expect non-null.
  - `T-CRON6 never-fires returns empty` —
    `nextCronExecutions("0 0 30 2 *", "UTC", new Date("2026-08-05T12:00:00Z"))`
    returns an array without throwing (allow `[]` or a partial list).
  - `T-CRON7 deterministic next 3` — with `now = new Date("2026-08-05T12:00:00Z")`,
    `nextCronExecutions("0 10 * * 1-5", "UTC", now)` returns 3 elements, each
    `getUTCHours() === 10`, all within next ~8 days, strictly increasing.
- **e2e tests:** none.
- **Note:** every test pins a fixed `now`; none reads the wall clock (D6).
- **Done:** `npm --prefix frontend run test -- --run src/lib/__tests__/cron.test.ts`
  passes all T-CRON*.

---

## Phase gates

- **Fmt/Lint:** `npm --prefix frontend run lint` (eslint `--max-warnings 0`)
- **Build (type check):** `npm --prefix frontend run build`
- **Test subset:** `npm --prefix frontend run test -- --run src/lib/__tests__/cron.test.ts`

## Phase done criterion
`cron-parser` is a dependency, `src/lib/cron.ts` exports the four functions,
and all T-CRON* tests pass. Only `package.json`, `package-lock.json` (both
under frontend) and the two new files may have changed — no existing application
code was touched.