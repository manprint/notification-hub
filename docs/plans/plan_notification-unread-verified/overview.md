# Notification unread/verified toggle — Plan Overview

> **Status:** planning | **Supervisor authored:** 2026-08-05
> **Folder:** `docs/plans/plan_notification-unread-verified/`

## Goal

Ogni notifica ottiene due stati booleani indipendenti e commutabili: `status`
(`read`/`unread`, gia' esistente) e `verified` (nuovo). Nelle pagine elenco e
dettaglio compaiono due pulsanti per riga/notifica: uno che commuta
lettura ("Segna come letta" / "Segna come non letta") e uno che commuta
verifica ("Segna come verificata" / "Segna come non verificata"). Nessuna
selezione e' permanente; ogni clic persiste via `PATCH /api/v1/notifications/{id}`
e la UI si aggiorna. Zero regressioni: `unread_count`, filtri, bulk-read e
permessi restano invariati.

```
Scenario di riferimento:
1. Operatore apre /notifications. Riga n1 (status=unread, verified=false):
   pulsante "Segna come letta" e "Segna come verificata".
2. Click "Segna come letta"  -> PATCH {status:"read"}  -> pill "Letta",
   pulsante diventa "Segna come non letta".
3. Click "Segna come non letta" -> PATCH {status:"unread"} -> stato ripristinato.
4. Click "Segna come verificata"  -> PATCH {verified:true}  -> pill "Verificata",
   pulsante diventa "Segna come non verificata".
5. Click "Segna come non verificata" -> PATCH {verified:false} -> ripristinato.
6. Gli stessi controlli esistono su /notifications/{id}.
7. Ogni toggle di verified NON cambia unread_count. Bulk-read NON tocca verified.
```

## Design decisions

| # | Decision | Consequence |
|---|----------|-------------|
| **D1** | Riuso di `PATCH /notifications/{id}` per entrambi i toggle: `MarkStatusIn` diventa `{status?: …, verified?: bool}`, almeno uno obbligatorio | Un solo endpoint, retro-compatibile (chi manda solo `status` non cambia); body vuoto -> 422 |
| **D2** | Nuova colonna `notifications.verified BOOLEAN NOT NULL DEFAULT false`, migrazione `0014` | Tutte le righe esistenti nascono "non verificate"; nessun enum DB; nessun indice nuovo |
| **D3** | Nessun filtro/query param per `verified` in lista | Scope minimo: verified e' solo un pill; API di query invariata |
| **D4** | Toggle presenti sia in elenco sia in dettaglio | UX consistente; invalidate su entrambe le query; due file di test |
| **D5** | Pulsante lettura sempre visibile, etichetta commutata (D5: "non letta" visibile quando read) | Il test FE esistente "segna come letta e il pulsante sparisce" va riscritto (behavior change, richiamato forte in phase_03) |
| **D6** | Stato verified come pill nella colonna "Stato" e nell'header del dettaglio, riuso di `.status-pill` + variante `.status-pill.verified` (accent) | Stile consistente, aggiunta CSS minima |
| **D7** | Niente optimistic update: dopo il PATCH si invalida la query (stesso pattern odierno) | Semplice, coerente col codice esistente; feedback leggermente piu' lento |

## Architecture summary

Backend: colonna `verified` + body PATCH esteso (D1/D2); lista e dettaglio
espongono `verified`. Frontend: due funzioni `setStatus`/`setVerified` in
elenco e dettaglio che chiamano `apiPatch` e invalidano le query
`["notifications"]` / `["notification", id]`; colonna azioni con i due pulsanti,
pill di stato accanto a `StatusPill`. Nessun cambio a RLS, authz o indici.

## Phases

| Phase | File | Primary assignment | Shippable alone? |
|-------|------|-------|-----------------|
| 0 — Backend: colonna verified + API toggle | [phase_01.md](phase_01.md) | `agent:deepseek-v4-flash` | yes |
| 1 — Frontend: lista notifiche | [phase_02.md](phase_02.md) | `agent:deepseek-v4-flash` | yes |
| 2 — Frontend: dettaglio notifica | [phase_03.md](phase_03.md) | `agent:deepseek-v4-flash` | yes |
| 3 — Regressione, docs, polish layout | [phase_04.md](phase_04.md) | `agent:deepseek-v4-flash` | yes |

## Reuse map (top candidates)

| Need | Reuse | Location |
|------|-------|----------|
| PATCH status notifica | `mark_notification_status` | `backend/app/api/v1/notifications.py:294` |
| Enum stato | `NotificationStatus` | `backend/app/db/types.py:71` |
| Loader 404 + authz | `_get_notification_or_404` | `backend/app/api/v1/notifications.py:208` |
| Costruzione risposta lista | `NotificationListItemOut(...)` | `backend/app/api/v1/notifications.py:184` |
| Costruzione risposta dettaglio | `NotificationDetailOut(...)` | `backend/app/api/v1/notifications.py:244` e `:310` |
| Client PATCH FE | `apiPatch` | `frontend/src/api/client.ts:211` |
| markRead elenco | `markRead` | `frontend/src/pages/NotificationsPage.tsx:66` |
| markRead dettaglio | `markRead` | `frontend/src/pages/NotificationDetailPage.tsx:31` |
| Pill | `.status-pill` | `frontend/src/styles.css:294` |
| Bottone | `button` | `frontend/src/styles.css:51` |
| Toolbar | `.toolbar` | `frontend/src/styles.css:329` |
| Mock lista msw | handlers `:414` | `frontend/src/api/mocks/handlers.ts` |
| Harness test FE | `renderWithProviders` | `frontend/src/pages/__tests__/testUtils.tsx:7` |
| Fixture e2e backend | `api_client`, `two_tenants`, `owner_token` | `backend/tests/conftest.py` (uso in `tests/e2e/test_consumption.py:120`) |
| Template migrazione | `0013_execution_phase.py` | `backend/alembic/versions/0013_execution_phase.py` |

## Invariants

- **I-1:** `unread_count` dipende SOLO da `status`; `verified` non lo influenza.
- **I-2:** RLS/authz invariati: entrambi i toggle passano da `_get_notification_or_404` + `assert_group_access` (`write=False`).
- **I-3:** `bulk-read` segna solo `status=read`; non tocca `verified`.
- **I-4:** Retro-compat: body PATCH con solo `status` si comporta identico a prima (guardia: `test_patch_segna_letta_e_bulk_read` + `test_mark_status_schema`).

## Risk register

| Risk | Mitigation |
|------|-----------|
| Rendere `status` opzionale nel PATCH rompe un client esistente | Retro-compat: i client mandano gia' `status`; guardia I-4 con i test preesistenti (phase 1) |
| Test FE esistente "il pulsante sparisce" rompe col nuovo UX | Riscrittura esplicita in phase_03, sub-phase 3.1 |
| msw senza handler PATCH -> 404 nei test | Handler PATCH globale aggiunto in phase_02 sub-phase 2.1 |
| Campo nuovo `verified` obbligatorio nelle response rompe typecheck FE | Tipi + fixture aggiornati prima di toccare le pagine (phase_02 sub-phase 2.1) |
| Layout riga affollato con due pulsanti | Colonna azioni flex con wrap + pill compatte (phase_02 sub-phase 2.2), check manuale phase_04 |

## Assignment summary

| Position | Configured name | Responsibility |
|----------|-----------------|----------------|
| agent-1 | `deepseek-v4-flash` | Scope, design, decomposition, approval. Review finale marcata come self-review |
| agent-2 | `deepseek-v4-flash` | Implementazione di tutte le fasi (single-agent mode) |
| agent-3+ | `deepseek-v4-flash` | Esplorazione e lavoro meccanico (single-agent mode) |
