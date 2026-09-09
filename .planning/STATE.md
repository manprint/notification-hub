---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 8
current_phase_name: Cross-Layer Verification
status: complete
stopped_at: Milestone verified against the code in the pre-staging review
last_updated: "2026-09-09T00:00:00.000Z"
last_activity: 2026-09-09
last_activity_desc: >-
  Pre-staging review: every roadmap phase verified against the real code, the two
  genuinely missing criteria implemented (member role on notification mutations,
  status/verified filters on API and UI). See docs/REVIEW.md "Verifica 3".
progress:
  total_phases: 8
  completed_phases: 8
  total_plans: 0
  completed_plans: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-04)

**Core value:** Operators can reliably identify, filter, acknowledge, and verify notification state without losing delivery or tenant isolation guarantees.
**Current focus:** Phase 1 — Notification State Model

## Current Position

Phase: 8 of 8 (Cross-Layer Verification)
Status: Complete — milestone verified against the code
Last activity: 2026-09-09 — Pre-staging review: roadmap reconciled with the
implementation, missing criteria closed, gates and containerized smoke green.

Progress: [██████████] 100%

Il lavoro di questa milestone è passato dai piani in `docs/plans/`
(`plan_notification-unread-verified`, `plan_cron-validation-preview`) e non da
questa cartella, che era rimasta a "Phase 1 context gathered". La revisione
pre-staging ha verificato ogni criterio di successo contro il codice reale:
vedi `.planning/ROADMAP.md` per lo stato per fase e `docs/REVIEW.md`
("Verifica 3") per i difetti trovati e corretti.

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| — | — | — | — |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

- Verification is independent from read state.
- Only member, admin, and owner may mutate notification states.
- Cron previews are live, server-authoritative, and time-zone aware.

- Le mutazioni di stato delle notifiche richiedono il ruolo `member`: un
  `viewer` legge e riceve 403 (chiuso nella revisione pre-staging, D3).
- `status` e `verified` sono filtri indipendenti e combinabili, esposti nell'URL
  della pagina notifiche (chiuso nella revisione pre-staging, D7).

### Pending Todos

None.

### Blockers/Concerns

- ~~Phase 6 planning should choose between a dedicated preview endpoint and an extension of the receiver response for unsaved input.~~ **Risolto:** la
  validazione autorevole del cron sta negli schemi Pydantic dei receiver (un
  cron non valido non si persiste nemmeno bypassando la UI) e la preview delle
  prossime esecuzioni è calcolata lato client (`frontend/src/lib/cron.ts`).
  Divergenza rispetto alla roadmap, documentata in `.planning/ROADMAP.md` fase 7.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-08-04T21:20:00.141Z
Stopped at: Phase 1 context gathered
Resume file: .planning/phases/01-notification-state-model/01-CONTEXT.md
