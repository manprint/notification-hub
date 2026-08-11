# Notification unread/verified toggle — Resume

> **Next:** nessuno — tutte le fasi DONE
> **Last updated:** 2026-08-05

## Phase status

| Phase | File | Status | Notes |
|-------|------|--------|-------|
| 0 — Backend verified + API | phase_01.md | `DONE` | colonna + migrazione 0014, schemi, handler, T-VER1..4 |
| 1 — Frontend lista | phase_02.md | `DONE` | tipi/fixture/msw, setStatus/setVerified, T-LIST1..4 |
| 2 — Frontend dettaglio | phase_03.md | `DONE` | setStatus/setVerified, pill, T-DET1..3, riscrittura "pulsante sparisce" |
| 3 — Regressione, docs, polish | phase_04.md | `DONE` | gates verdi, spec sincronizzata, check layout 1-6 passato |

Status values: `TODO` · `IN_PROGRESS` · `DONE` · `SKIPPED` · `BLOCKED`

## Tests

| ID | Type | Status | Notes |
|----|------|--------|-------|
| T-SCH1 / T-SCH2 | unit | `DONE` | MarkStatusIn: only-verified ok; empty body 422 |
| T-VER1 | e2e | `DONE` | PATCH verified:true persiste e compare in dettaglio |
| T-VER2 | e2e | `DONE` | PATCH status:unread torna indietro; verified non tocca unread_count |
| T-VER3 | e2e | `DONE` | PATCH body vuoto -> 422 |
| T-VER4 | e2e | `DONE` | lista e dettaglio espongono verified (default false) |
| T-LIST1..T-LIST4 | frontend | `DONE` | etichette pulsanti; PATCH {status:unread}; PATCH {verified:true}; pill |
| T-DET1..T-DET3 | frontend | `DONE` | dettaglio: pulsanti presenti; toggle verified; riscrittura "pulsante sparisce" |

## Docs
| File | Status | Notes |
|------|--------|-------|
| `docs/notifyhub-spec.md` | `DONE` | campo `verified` nella tabella notifications; toggle read/unread + verified; riga PATCH endpoint |
| `docs/OPERAZIONI.md` | `SKIPPED` | nessun runbook impattato |

## Open blockers
- none

## Decisions changed at runtime
- `test_notification_list_item_schema` (unit backend) aggiornato con `verified=False`: il campo e' obbligatorio nello schema di output (coerente con migrazione NOT NULL).
