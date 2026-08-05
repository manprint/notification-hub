# Notifications Page Redesign — Resume

> **Next:** — (complete)
> **Last updated:** 2026-08-05

## Phase status

| Phase | File | Status | Notes |
|-------|------|--------|-------|
| 0 — Scaffolding | phase_01.md | `DONE` | handler bulk-read + GroupList |
| 1 — Table visual fixes | phase_02.md | `DONE` | css nowrap + .status-cell + row-actions |
| 2 — Group-first navigation | phase_03.md | `DONE` | grid landing + enabled hook + back link |
| 3 — States, polish, docs, regression | phase_04.md | `DONE` | edge tests + T-ACCEPT1; doc update N/A (no doc describes the page layout) |

Status values: `TODO` · `IN_PROGRESS` · `DONE` · `SKIPPED` · `BLOCKED`

## Tests

| ID | Type | Status | Notes |
|----|------|--------|-------|
| T-BULK1 | unit | `DONE` | `bulk_read_posts_body_and_succeeds` |
| T-GRP0 | unit | `DONE` | GroupList 5 tests |
| T-GRP0-EMPTY | unit | `DONE` | covered by `group_list_empty_message` |
| T-SEVR5 | unit | `DONE` | `severity_badge_never_wraps` (class assert; jsdom non applica CSS) |
| T-ALIGN2 | unit | `DONE` | `status_cell_wraps_pills_aligned` |
| T-ROW4 | unit | `DONE` | `action_buttons_stay_on_same_row` |
| T-GRP1 | e2e | `DONE` | grid, no notifications call |
| T-GRP2 | e2e | `DONE` | click -> scoped table |
| T-GRP3 | e2e | `DONE` | back link + no group combobox |
| T-GRP4 | e2e | `DONE` | filters group-scoped (replaces T-UI9) |
| T-EMPTY2 | e2e | `DONE` | empty group message |
| T-ERR1 | e2e | `DONE` | groups 500 -> banner |
| T-ACCEPT1 | e2e | `DONE` | full reference flow |

## Docs

| File | Status | Notes |
|------|--------|-------|
| `docs/OPERAZIONI.md` | `N/A` | nessun documento descrive il layout della pagina notifiche; nulla da correggere |

## Open blockers

- none

## Decisions changed at runtime

- Test toHaveStyle → class assertions: jsdom non applica styles.css, quindi i test di fase 1 verificano la classe che porta la regola CSS invece del computed style.
- Doc update (3.3) N/A: nessun file descrive il vecchio dropdown "Tutti i gruppi".
