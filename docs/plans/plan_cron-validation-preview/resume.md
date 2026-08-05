# Cron validation + next-executions preview — Resume

> **Next:** none — all phases DONE
> **Last updated:** 2026-08-05

## Phase status

| Phase | File | Status | Notes |
|-------|------|--------|-------|
| 0 — Cron lib + dep | [phase_01.md](phase_01.md) | `DONE` | cron-parser@4.9 + src/lib/cron.ts |
| 1 — Validation wiring | [phase_02.md](phase_02.md) | `DONE` | blocks save, inline error, tz guard |
| 2 — Next-3 preview | [phase_03.md](phase_03.md) | `DONE` | live 3-exec preview + CSS |

## Tests

| ID | Type | Status | Assertion |
|----|------|--------|-----------|
| T-CRON1 | unit | `DONE` | valid 5-field crons → null |
| T-CRON2 | unit | `DONE` | empty / wrong count → `5 campi` |
| T-CRON3 | unit | `DONE` | out-of-range / garbage → `non valida` |
| T-CRON4 | unit | `DONE` | over-long → `100 caratteri` |
| T-CRON5 | unit | `DONE` | timezone accept/reject |
| T-CRON6 | unit | `DONE` | never-fire returns array w/o throw |
| T-CRON7 | unit | `DONE` | 3 ascending next executions |
| T-VAL1 | e2e | `DONE` | invalid cron blocks PATCH + alert |
| T-VAL2 | e2e | `DONE` | live inline `5 campi` before submit |
| T-VAL3 | e2e | `DONE` | corrupted saved tz rejected, no PATCH |
| T-PRE1 | e2e | `DONE` | 3 distinct preview items |
| T-PRE2 | e2e | `DONE` | recompute on tz change, wall-time `03:00` |

## Docs
| File | Status | Notes |
|------|--------|-------|
| overview.md | `DONE` | — |
| resume.md | `DONE` | — |
| phase_01.md, phase_02.md, phase_03.md | `DONE` | implemented |

## Open blockers
- none

## Decisions changed at runtime
- **T-PRE2**: the displayed wall-clock time is the cron's local time in the chosen
  tz (03:00 in both UTC and Rome), so rendered strings are legitimately
  identical across tz; the test asserts recompute correctness instead, and tz
  sensitivity is proven in `cron.test.ts`. (plan divergence, documented)
- **T-VAL3 / existing test**: with the live inline alert added, the pre-existing
  "5 campi" test now sees two alert nodes and was switched to
  `findAllByRole("alert")` (plan said "unchanged"; inline alert makes that
  impossible — function preserved).

## Gate commands
- Lint: `npm --prefix frontend run lint` — clean
- Build: `npm --prefix frontend run build` — clean
- Tests: `npm --prefix frontend run test -- --run` — 128 pass
- Coverage: thresholds hold (87.4/79.6/65.4/87.4 vs 85/78/60/85)