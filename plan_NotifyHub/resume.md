# NotifyHub — Resume

> **Next:** phase_02.md § 1.6 — Alembic e prima migrazione dello schema
> **Last updated:** 2026-08-01

## Phase status

| Fase | File | Stato | Note |
|------|------|-------|------|
| 0 — Scaffolding, tooling, gate | phase_01.md | `DONE` | network bridge fixed, all 6 tests green |
| 1 — Modello dati, migrazioni, RLS | phase_02.md | `IN_PROGRESS` | 1.1-1.5 DONE (base, types, 9 models, 12 unit tests), 1.6-1.10 TODO |
| 2 — Nucleo trasversale | phase_03.md | `TODO` | — |
| 3 — Autenticazione e identita | phase_04.md | `TODO` | — |
| 4 — Management di dominio | phase_05.md | `TODO` | — |
| 5 — Ingestion | phase_06.md | `TODO` | — |
| 6 — Outbound e outbox | phase_07.md | `TODO` | — |
| 7 — API di consultazione | phase_08.md | `TODO` | — |
| 8 — Manutenzione, quote, osservabilita | phase_09.md | `TODO` | — |
| 9 — Dashboard React | phase_10.md | `TODO` | — |
| 10 — Deploy, smoke, documentazione | phase_11.md | `TODO` | — |

Valori ammessi: `TODO` · `IN_PROGRESS` · `DONE` · `SKIPPED` · `BLOCKED`

Aggiorna la riga quando inizi (`IN_PROGRESS`) e dopo il sign-off di Opus (`DONE`). Nelle Note registra le sotto-fasi concluse e i test scritti, per esempio: `0.1-0.4 DONE, T-ENV1 e T-SCAF1..5 verdi`.

## Tests

Una riga per famiglia. Aggiorna lo stato quando la fase che la produce e conclusa; nelle Note metti quanti test sono effettivamente presenti e verdi.

| Famiglia | Tipo | Fase | Stato | Cosa dimostra |
|----------|------|------|-------|---------------|
| T-ENV1 | unit | 0 | `DONE` | `re2` installato e funzionante |
| T-SCAF1..5 | e2e, integration | 0 | `DONE` | 6 test green, network_mode host per docker-compose.test.yml |
| T-DDL1..5 | integration | 1 | `TODO` | migrazioni reversibili, trigger e CHECK attivi |
| T-RLS1..9 | integration | 1 | `TODO` | isolamento fra tenant, diniego di default, ruoli senza scrittura |
| T-CORE1..6 | unit, e2e, integration | 2 | `TODO` | log senza segreti, errori RFC 7807, cripto, prontezza reale |
| T-AUTH1..22 | unit, e2e, integration | 3 | `TODO` | login, rotazione e riuso dei refresh, ruoli, ultimo owner, inviti |
| T-MGMT1..17 | unit, e2e | 4 | `TODO` | gruppi con conferma, slug, regole RE2, cap del tenant |
| T-ING1..24 | unit, e2e, integration | 5 | `TODO` | 404 uniforme, limiti, normalizzazione, offload, idempotenza |
| T-OUT1..26 | unit, e2e, integration | 6 | `TODO` | risoluzione destinazioni, outbox, ordine commit-enqueue, ritenti |
| T-CONS1..20 | unit, e2e | 7 | `TODO` | cursore, lista senza corpo, download integro, cancellazione accodata |
| T-MAINT1..23 | unit, integration, e2e | 8 | `TODO` | purge, riconciliazione, orfani, quote, metriche |
| T-UI1..19 | unit | 9 | `TODO` | guardia ruoli, cursore, nessun webhook in chiaro |
| T-E2E1 | accettazione | 10 | `TODO` | `scripts/smoke.sh` esce con 0 su stack pulito |

## Verifiche di autenticita richieste

Sono controlli in cui si rompe deliberatamente il codice per confermare che il test se ne accorga. Vanno eseguiti e poi ripristinati; annota qui l'esito.

| Verifica | Fase | Test che deve diventare rosso | Esito |
|----------|------|-------------------------------|-------|
| Rimuovere `SET LOCAL app.tenant_id` | 1.10 | T-RLS3, T-RLS6, T-RLS9 | `TODO` |
| Spostare l'accodamento dentro la transazione | 6.5 | T-OUT12 | `TODO` |
| Far leggere il payload al worker | 6.8 | T-OUT20 | `TODO` |
| Invertire la condizione sugli oggetti referenziati | 8.5 | T-MAINT17 | `TODO` |
| Spegnere il worker prima del passo 16 dello smoke | 10.4 | T-E2E1 | `TODO` |

## Docs

| File | Stato | Note |
|------|-------|------|
| README.md | `TODO` | avvio rapido, prima notifica, test |
| docs/OPERAZIONI.md | `TODO` | esercizio, backup congiunto Postgres piu MinIO, job |
| notifyhub-spec.md | `DONE` | v0.3, fonte di verita, non va modificata dall'implementatore |

## Open blockers

- nessuno

## Decisions changed at runtime

- nessuna
