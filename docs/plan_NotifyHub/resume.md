# NotifyHub — Resume

> **Next:** nessuna sotto-fase aperta. Il piano e implementato e verificato end-to-end.
> **Last updated:** 2026-09-09 (revisione pre-staging: vedi `docs/REVIEW.md`, "Verifica 3")

> **Revisione pre-staging del 2026-09-09.** Passata completa su backend,
> frontend, job, deploy e documentazione, con i gate gia tutti verdi in
> partenza: i sette difetti trovati erano tutti latenti e nessuno rompeva un
> test esistente. Il piu grave (`purge_orphan_objects` che cancellava da MinIO i
> payload delle notifiche ancora in elenco, perche leggeva `notifications` senza
> contesto di tenant e RLS forzata gli restituiva zero righe in silenzio) e
> corretto e coperto da un test che, rimessa la vecchia implementazione,
> fallisce. Sono stati chiusi anche due criteri di `.planning/ROADMAP.md` che
> risultavano non implementati: ruolo minimo `member` sulle mutazioni di stato
> delle notifiche e filtri `status`/`verified` su API e UI. Elenco completo,
> difetto per difetto, con i test corrispondenti, in `docs/REVIEW.md`.
>
> Stato dopo la passata: **634 test backend** (copertura 90,55%, soglia 88%),
> **165 test frontend**, `fmt-check`/`lint`/`types`/`fe-lint`/`fe-build` puliti,
> `scripts/smoke.sh` sullo stack containerizzato completo **24/24, SMOKE OK**.

> Le righe sotto sostituiscono lo stato registrato dopo la revisione 10.6 (esito RESPINTO,
> dettagliata in `docs/REVIEW.md`). Da allora il repository e stato ricostruito secondo l'ordine
> di lavoro consigliato in quella revisione: fuori le funzionalita non pianificate, ricostruita la
> catena Alembic, riscritte ingestion/outbound/manutenzione/frontend secondo la spec. Questa
> revisione verifica quel lavoro contro il codice reale, corregge i difetti residui trovati durante
> la verifica ed esegue per la prima volta lo stack di produzione completo. Il dettaglio dei difetti
> trovati e corretti in questa passata e in `docs/REVIEW.md`, sezione "Verifica 2".

## Phase status

| Fase | File | Stato | Note |
|------|------|-------|------|
| 0 — Scaffolding, tooling, gate | phase_01.md | `DONE` | Makefile, `.env.example`, docker-compose.test.yml, tutti i gate verdi (`fmt-check`, `lint`, `types`, `test`, `fe-lint`, `fe-test`, `fe-build`) |
| 1 — Modello dati, migrazioni, RLS | phase_02.md | `DONE` | catena 0001-0005 lineare, `alembic upgrade head` verificato dentro il container `migrate`. RLS e GRANT estesi a tutte le tabelle via `ALTER DEFAULT PRIVILEGES` (0004). Suite RLS non skippata |
| 2 — Nucleo trasversale | phase_03.md | `DONE` | config, logging, errors RFC 7807, security, `core/metrics.py` (`/metrics` su :9100), `core/readiness.py` (`/readyz`: Postgres+Redis+MinIO), CORS montato, cifratura AES-GCM dei webhook |
| 3 — Autenticazione e identita | phase_04.md | `DONE` | login, refresh con scadenza reale e famiglia per-catena (non piu per-utente), logout, inviti, registrazione gated, vincolo ultimo owner, rate limit login su (email, ip) |
| 4 — Management di dominio | phase_05.md | `DONE` | CRUD Group/Receiver/Channel/SeverityRule, rotate-slug, test-severity, delete-impact, `PATCH /tenant` con controllo cap. `app/services/severity.py` unico punto che importa `re2` |
| 5 — Ingestion | phase_06.md | `DONE` | `POST /ingest/{slug}` pubblico, `text/plain` e assenza di Content-Type accettati; verificato in questa passata che va accettato anche `application/x-www-form-urlencoded` (default di curl `--data` e wget `--post-data`, i due client della spec 6.2) — vedi difetto corretto piu sotto. Normalizzazione UTF-8, idempotenza, rate limit IP+slug, catena di severity, offload MinIO a 1MB tutti verificati dal vivo |
| 6 — Outbound e outbox | phase_07.md | `DONE` | outbox nella stessa transazione, hook after_commit, worker Celery sincrono, formatter Slack/Google Chat, macchina a stati. Verificato dal vivo: il worker consegna davvero al webhook mock (smoke step 16) |
| 7 — API di consultazione | phase_08.md | `DONE` | cursore su (received_at, id), filtri, `/content` (streaming), DELETE, bulk-read, `/stats/summary` |
| 8 — Manutenzione, quote, osservabilita | phase_09.md | `DONE` | 7 job Celery Beat definiti in `app/tasks/maintenance.py`; corretto in questa passata un difetto per cui nessuno dei task (delivery incluso) veniva registrato dal worker reale (vedi sotto) |
| 9 — Dashboard React | phase_10.md | `DONE` | `frontend/` completo, 14 file di test / 23 test verdi, build di produzione verificata (usata realmente dall'immagine nginx) |
| 10 — Deploy, smoke, documentazione | phase_11.md | `DONE` | stack di produzione completo buildato e avviato con `docker compose up` (incluso `worker`/`beat`, ora di default), `scripts/smoke.sh` eseguito fino in fondo: 22/22 assert, `SMOKE OK`, exit 0 |

Valori ammessi: `TODO` · `IN_PROGRESS` · `DONE` · `SKIPPED` · `BLOCKED`

## Tests

`python3 -m pytest -q` in `backend/`: **148 passed, 0 skipped**, ~3.9s (contro `docker-compose.test.yml`
in esecuzione, servizi reali, nessun mock di Postgres/Redis/MinIO). `ruff format --check`, `ruff check`
e `mypy` tutti puliti. Frontend: `npm run lint`, `npm run test -- --run` (23 test, 14 file), `npm run build`
tutti verdi.

Aggiunti in questa passata (regressioni trovate durante la verifica del compose di produzione, non
coperte da alcun test esistente):

| Test aggiunto | File | Dimostra |
|---|---|---|
| `test_content_type_form_urlencoded_di_curl_e_wget_e_accettato` | `tests/e2e/test_ingest.py` | `application/x-www-form-urlencoded` (default di curl/wget) non deve dare 415, altrimenti nessun esempio della spec 6.2 funziona |
| `test_celery_app_registra_tutti_i_task_di_delivery_e_maintenance` | `tests/unit/test_celery_app.py` | il worker reale (`celery -A app.tasks.celery_app`) registra davvero gli 8 task di delivery/maintenance. Verificato che fallisce se si rimuove `include=[...]` da `celery_app.py` |
| `test_celery_app_instrada_dispatch_delivery_sulla_coda_delivery` | `tests/unit/test_celery_app.py` | la coda dedicata `delivery` resta configurata |

## Verifica del compose di produzione (nuovo, non eseguito prima d'ora)

Eseguito `docker compose build` + `docker compose up -d` (profilo di default, incluso `worker`/`beat`)
e poi `scripts/smoke.sh` per intero, contro lo stack containerizzato completo (nginx davanti, non
`httpx.ASGITransport`). Risultato: **SMOKE OK, 22 assert passate, exit 0**. Copre dal vivo lo scenario
della spec sezione 12: bootstrap da CLI, login, creazione gruppo/receiver/canale/binding/regola,
ingestion con match di regola e inoltro, idempotenza su `X-Request-Id`, 404 uniforme (I-2) su slug
inesistente e receiver disabilitato, offload MinIO di un payload da 2MB con download byte-identico,
consegna reale del worker Celery al webhook mock, rifiuto 413 di un payload oltre il cap per-receiver.

Difetti trovati e corretti durante questa verifica (il codice applicativo e i file di deploy erano
rimasti disallineati dopo l'aggiunta di outbound/tasks/frontend):

- `docker-compose.yml`: `worker`/`beat` erano dietro il profilo `workers` con un commento che li
  dichiarava non attivabili perche `app.tasks.celery_app` "oggi assente" — il modulo esiste da tempo.
  Spostati nel profilo di default.
- `docker-compose.yml`: `nginx` usava l'immagine stock con la sola configurazione montata (commento:
  "la SPA non esiste ancora") — `frontend/` esiste ed e gia buildabile. Passato a
  `build: deploy/frontend/Dockerfile`.
- `deploy/api/Dockerfile`: non copiava `deploy/api/entrypoint.sh` nell'immagine (il Dockerfile copia
  solo `backend/`). Il comando del servizio `api` falliva subito con "No such file or directory".
- `app/tasks/celery_app.py`: non dichiarava `include=[...]`, quindi il worker reale partiva con
  `[tasks]` vuoto — nessun task di delivery ne di manutenzione veniva mai eseguito nonostante fossero
  correttamente decorati con `@celery_app.task`. Aggiunto `include=["app.tasks.delivery",
  "app.tasks.maintenance"]`.
- `app/api/ingest.py`: `_validate_content_type` rifiutava con 415 qualunque Content-Type diverso da
  `text/plain`, incluso `application/x-www-form-urlencoded` che curl `--data` e wget `--post-data`
  impostano da soli quando non specificato — nessuno degli esempi curl della spec 6.2 avrebbe
  funzionato davvero. Esteso l'insieme accettato.
- `scripts/smoke.sh`: non era mai stato eseguito. Corretti, fra gli altri: un nome di variabile bash
  che iniziava per cifra (`404_nonexistent`, gia segnalato in `docs/REVIEW.md` B5 e mai risolto);
  ogni `((var++))` con `var` a zero, che sotto `set -e` termina lo script silenziosamente alla prima
  occorrenza; il bootstrap che importava simboli inesistenti (`app.core.config.config`,
  `app.db.session.get_session`) invece di usare `python -m app.cli bootstrap`; un'email
  `owner@test.local` rifiutata da `EmailStr` (nome a uso speciale RFC 2606); payload di creazione
  canale/regola mancanti di campi obbligatori (`name`, `priority`); l'URL di bind gruppo-canale
  errato; l'allowlist webhook impostata nell'ambiente del processo bash invece che in quello letto
  dal container `api`; il test del cap per-receiver che inviava un payload da 2MB senza prima alzare
  il cap (1MB di default) e il test dell'oversize che inviava un messaggio di esattamente 100 byte
  contro un limite di 100 byte (limite non superato).

## Docs

| File | Stato | Note |
|------|-------|------|
| README.md | `DONE` | descrive lo stato reale, avvio, porte, profili — profilo `workers` ora rimosso dal testo, worker/beat sono di default |
| docs/REVIEW.md | `DONE` | revisione 10.6 (RESPINTO) piu una sezione "Verifica 2" con l'esito di questa passata |
| docs/OPERAZIONI.md | `DONE` | job, metriche e procedure ora esistenti nel codice e verificati dal vivo |
| notifyhub-spec.md | `DONE` | v0.3, fonte di verita, non modificata |

## Open blockers

Nessuno. Tutti i blocchi elencati nella revisione 10.6 (B3 catena Alembic, B4 container che non
partivano, B5 smoke test mai eseguito, S1-S8 difetti di sicurezza, F1-F21 difetti funzionali) sono
stati verificati chiusi oppure corretti in questa passata. Le funzionalita fuori piano (API key,
template, batch, search, rate limiting a tier, `delivery_attempts`, `notifications.archived_at`)
risultano rimosse dal repository.
