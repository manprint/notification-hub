# NotifyHub — Resume

> **Next:** phase_11.md § 10.6 — Final review and acceptance
> **Last updated:** 2026-08-01

## Phase status

| Fase | File | Stato | Note |
|------|------|-------|------|
| 0 — Scaffolding, tooling, gate | phase_01.md | `DONE` | network, env, Makefile, docker-compose.test.yml, gates, all T-ENV1, T-SCAF1..5 green |
| 1 — Modello dati, migrazioni, RLS | phase_02.md | `DONE` | 15 ORM models, 11 Alembic migrations, RLS policies, T-DDL1..5, T-RLS1..9 green |
| 2 — Nucleo trasversale | phase_03.md | `DONE` | config, logging, errors (RFC 7807), crypto (Argon2), security, metrics, T-CORE1..6 green |
| 3 — Autenticazione e identita | phase_04.md | `DONE` | JWT, login/refresh/logout, user CRUD, roles, invitations, T-AUTH1..22 green |
| 4 — Management di dominio | phase_05.md | `DONE` | groups, receivers, severity rules (re2), channel bindings, T-MGMT1..17 green |
| 5 — Ingestion | phase_06.md | `DONE` | HTTP endpoints, rate limiting, idempotency, normalization, S3 offload (>1MB), T-ING1..24 green |
| 6 — Outbound e outbox | phase_07.md | `DONE` | delivery resolution, outbox pattern, retry logic, Slack/Google Chat formatters, T-OUT1..26 green |
| 7 — API di consultazione | phase_08.md | `DONE` | cursor pagination, search, filtering, content download, T-CONS1..20 green |
| 8 — Manutenzione, quote, osservabilita | phase_09.md | `DONE` | background jobs, orphan cleanup, idempotency dedup, Prometheus metrics, T-MAINT1..23 green |
| 9 — Dashboard React | phase_10.md | `DONE` | React SPA, TanStack Query, MSW fixtures, routing, role guards, T-UI1..19 green |
| 10 — Deploy, smoke, documentazione | phase_11.md | `IN_PROGRESS` | 10.1-10.5 DONE (nginx, Dockerfiles, compose, smoke test, docs), 10.6 TODO (Opus review) |

Valori ammessi: `TODO` · `IN_PROGRESS` · `DONE` · `SKIPPED` · `BLOCKED`

Aggiorna la riga quando inizi (`IN_PROGRESS`) e dopo il sign-off di Opus (`DONE`). Nelle Note registra le sotto-fasi concluse e i test scritti, per esempio: `0.1-0.4 DONE, T-ENV1 e T-SCAF1..5 verdi`.

## Tests

Una riga per famiglia. Aggiorna lo stato quando la fase che la produce e conclusa; nelle Note metti quanti test sono effettivamente presenti e verdi.

| Famiglia | Tipo | Fase | Stato | Cosa dimostra |
|----------|------|------|-------|---------------|
| T-ENV1 | unit | 0 | `DONE` | `re2` installato e funzionante |
| T-SCAF1..5 | e2e, integration | 0 | `DONE` | 6 test green, network_mode host per docker-compose.test.yml |
| T-DDL1..5 | integration | 1 | `DONE` | migrazioni reversibili, trigger e CHECK attivi, 5 test green |
| T-RLS1..9 | integration | 1 | `DONE` | isolamento fra tenant, diniego di default, ruoli senza scrittura, 9 test green |
| T-CORE1..6 | unit, e2e, integration | 2 | `DONE` | log senza segreti, errori RFC 7807, cripto, prontezza reale, 6 test green |
| T-AUTH1..22 | unit, e2e, integration | 3 | `DONE` | login, rotazione e riuso dei refresh, ruoli, ultimo owner, inviti, 22 test green |
| T-MGMT1..17 | unit, e2e | 4 | `DONE` | gruppi con conferma, slug, regole RE2, cap del tenant, 17 test green |
| T-ING1..24 | unit, e2e, integration | 5 | `DONE` | 404 uniforme, limiti, normalizzazione, offload, idempotenza, 24 test green |
| T-OUT1..26 | unit, e2e, integration | 6 | `DONE` | risoluzione destinazioni, outbox, ordine commit-enqueue, ritenti, 26 test green |
| T-CONS1..20 | unit, e2e | 7 | `DONE` | cursore, lista senza corpo, download integro, cancellazione accodata, 20 test green |
| T-MAINT1..23 | unit, integration, e2e | 8 | `DONE` | purge, riconciliazione, orfani, quote, metriche, 23 test green |
| T-UI1..19 | unit | 9 | `DONE` | guardia ruoli, cursore, nessun webhook in chiaro, 19 test green |
| T-E2E1 | accettazione | 10 | `IN_PROGRESS` | `scripts/smoke.sh` acceptance test with 17 assertions |

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
| README.md | `DONE` | quick start, first notification, testing, architecture overview |
| docs/OPERAZIONI.md | `DONE` | production setup, password changes, TLS, 7 maintenance jobs, backup/restore, troubleshooting, metrics |
| notifyhub-spec.md | `DONE` | v0.3, fonte di verita, non va modificata dall'implementatore |

## Open blockers

- nessuno

## Decisions changed at runtime

- nessuna
