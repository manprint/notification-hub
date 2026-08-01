# NotifyHub — Plan Overview

> **Status:** planning | **Opus authored:** 2026-08-01
> **Folder:** `plan_NotifyHub/`
> **Spec di riferimento:** `notifyhub-spec.md` v0.3 (unica fonte di verita funzionale)

## How to implement this plan

1. Leggi questo overview, poi `resume.md`. Vai alla sotto-fase indicata da `Next:`.
2. Apri **solo** quel file di fase. Esegui la sotto-fase esattamente come scritta, con il modello indicato nel tag `Model`. Non leggere altre fasi se non esplicitamente richiesto.
3. Esegui i gate della fase. Devono essere verdi prima che la sotto-fase sia considerata conclusa.
   **Un gate rosso non blocca subito — sali la scala di escalation:**
   (a) il modello assegnato ritenta (1-2 tentativi) usando gli anchor della sotto-fase e l'output del gate fallito;
   (b) se fallisce ancora, escalation a **Sonnet** con il contesto completo del fallimento;
   (c) se Sonnet non risolve, escalation a **Opus** per analisi della causa radice: Opus individua il difetto e scrive le istruzioni di fix passo-passo da far applicare al modello piu economico, oppure corregge lui il design;
   (d) marca `BLOCKED` e riporta **solo** se Opus ha bisogno di una decisione o di un'informazione che non possiede (requisito ambiguo, anchor mancante, dipendenza esterna) — in quel caso ripristina le modifiche rotte cosi che l'albero resti verde. Non passare mai alla sotto-fase successiva con un gate rosso.
4. Una sotto-fase e **DONE solo dopo il sign-off di Opus** su qualita e zero regressioni (nessun comportamento, test o invariante `I-*` preesistente rotto). Poi aggiorna `resume.md`: cambia stato (`TODO -> IN_PROGRESS` all'inizio, `-> DONE` dopo il sign-off), registra test scritti/eseguiti e documenti toccati nelle Note, sposta il puntatore `Next:` alla prima riga ancora `TODO`.
   Esempio di riga: `| 1.1 Struttura cartelle | DONE | 4 file creati, gates verdi |`.
5. Fermati o committa secondo le istruzioni dell'operatore per questa sessione.

**Regole vincolanti:**

- Rispetta la struttura di progetto definita in questo overview e i nomi indicati nelle fasi. Non inventare percorsi alternativi.
- Non creare cartelle nuove oltre a quelle elencate nella struttura qui sotto. Se una sotto-fase sembra richiederne una, **fermati e chiedi**.
- Nessuna emoji, nessuna icona decorativa, nessuna formattazione appariscente in codice, test, documentazione o messaggi di commit. Solo prosa tecnica.
- Non inventare mai API, file, flag, variabili d'ambiente o dipendenze non nominate nel piano. L'elenco delle dipendenze e chiuso ed e in fase 0.
- Se un anchor citato nel piano non esiste o non corrisponde, **fermati e chiedi**. Non indovinare.
- Ogni sotto-fase comportamentale deve avere almeno un test che **fallisce se la funzionalita viene rimossa**. Un test sempre verde non conta.
- La spec `notifyhub-spec.md` prevale su qualunque interpretazione. Se il piano e la spec divergono, fermati e segnala la divergenza.

## Goal

Costruire da zero NotifyHub come descritto in `notifyhub-spec.md` v0.3: un aggregatore di notifiche multi-tenant self-hosted, con ingestion HTTP su endpoint identificati da slug, isolamento dei dati tramite Row Level Security di PostgreSQL, offload su object store dei payload oltre 1MB, inoltro asincrono verso Slack e Google Chat con pattern outbox, dashboard React e deploy Docker Compose. Il criterio di accettazione osservabile e lo script `scripts/smoke.sh`, che su uno stack appena avviato riproduce integralmente lo scenario della sezione 12 della spec e termina con exit code 0.

```
                        internet
                            |
                     +------v------+   client_max_body_size 20m
                     |    nginx    |   proxy_request_buffering off su /ingest/
                     +--+-------+--+
                        |       |
              SPA React |       | /api/v1/*  e  /ingest/*
                        |       |
                     +--v-------v--+           +-------------------+
                     |     api     |---------->|  metrics :9100    |
                     |  (FastAPI)  |           |  (porta interna)  |
                     +--+---+---+--+           +-------------------+
                        |   |   |
      pool notifyhub_app|   |   |pool notifyhub_ingest
      pool notifyhub_auth|  |   |
                        |   |   +---------------------+
                        |   |                         |
                 +------v---v------+          +-------v-------+
                 |  PostgreSQL 16  |          |     MinIO     |
                 |  RLS forzata    |          |  payload >1MB |
                 +--------+--------+          +-------+-------+
                          ^                           ^
                          |                           |
                 +--------+--------+                  |
                 |  worker / beat  |------------------+
                 |  (Celery, sync) |
                 +--------+--------+
                          |
                     +----v----+
                     |  redis  |  broker, rate limit, idempotenza, contatori
                     +---------+
```

Scenario di riferimento (equivale a `scripts/smoke.sh`, fase 10):

```
1.  make up && make bootstrap
2.  login owner            -> 200, access_token
3.  POST /api/v1/groups                      -> 201 group "Server Produzione"
4.  POST /api/v1/groups/{g}/receivers        -> 201 receiver, slug 22 caratteri
5.  POST /api/v1/channels  (webhook -> mock) -> 201, webhook_url mai in chiaro nella risposta
6.  POST /api/v1/groups/{g}/channels/{c}     -> 201 binding min_severity=error
7.  POST /api/v1/receivers/{r}/severity-rules pattern "FALL(ITO|IMENT)|ERROR" -> error
8.  curl -H "X-Request-Id: smoke-1" --data "Backup FALLITO: disco pieno su /var" /ingest/{slug}
        -> 201  {"severity":"error","severity_source":"rule","forwarded_to":1}
9.  stesso comando ripetuto                  -> 200 e header Idempotent-Replay: true
10. curl /ingest/slug-inesistente            -> 404, corpo identico al passo 12
11. PATCH receiver status=disabled
12. curl /ingest/{slug}                      -> 404, corpo byte-identico al passo 10
13. PATCH receiver status=active
14. curl --data-binary @2mb.txt /ingest/{slug}
        -> 201, notification con storage_backend=object
15. GET /api/v1/notifications/{id}/content   -> 2097152 byte identici al file inviato
16. il webhook mock ha ricevuto esattamente 1 POST, con testo troncato e link
17. exit 0
```

## Design decisions

Le decisioni funzionali sono gia chiuse nella spec (sezione 15). Qui stanno solo le decisioni **di implementazione** che la spec non fissa e che l'implementatore non deve reinventare.

| # | Decisione | Conseguenza |
|---|-----------|-------------|
| **D1** | Layout a due radici: `backend/` (Python) e `frontend/` (React), piu `deploy/` per configurazioni di infrastruttura e `scripts/` per gli script operativi. Nessun'altra cartella di primo livello. | Ogni sotto-fase nomina un percorso esatto. Una cartella non prevista e un errore, non una scelta. |
| **D2** | Dipendenze Python fissate in `backend/requirements.txt` e `backend/requirements-dev.txt` con vincolo `~=`. L'elenco e chiuso in fase 0. | L'implementatore non aggiunge pacchetti. Se ne serve uno non in lista, si ferma e chiede. |
| **D3** | Quattro ruoli Postgres, non tre: `notifyhub_owner` (proprietario dello schema, usato solo da Alembic) piu i tre di runtime della spec sezione 5.2. | Serve `DATABASE_URL_OWNER` oltre alle tre variabili della spec. Con `FORCE ROW LEVEL SECURITY` la RLS vale anche per il proprietario: nessun seeding di dati dentro le migrazioni. |
| **D4** | I ruoli e il database vengono creati da `deploy/postgres/initdb/00-roles.sql`, montato in `docker-entrypoint-initdb.d`. Le tabelle, le GRANT e le policy dalle migrazioni Alembic. | `CREATE ROLE` richiede il superutente e gira una sola volta, al primo avvio del volume. Ricreare i ruoli richiede `make reset-db`. |
| **D5** | Test su servizi reali (PostgreSQL, Redis, MinIO) avviati da `docker-compose.test.yml` su porte dedicate 5433 / 6380 / 9002. Nessun mock del database, nessun SQLite. | La RLS, i trigger e le policy sono la parte piu delicata del sistema e non sono testabili in memoria. `make test` richiede `make up-test`. |
| **D6** | L'API viene testata via `httpx.ASGITransport` contro l'app FastAPI in-process, con i servizi reali dietro. `scripts/smoke.sh` e l'unico test che passa da nginx e dallo stack completo. | Test veloci e deterministici, piu un'unica verifica del deploy reale in fase 10. |
| **D7** | L'accodamento dei task Celery passa da un'astrazione iniettabile `app/tasks/enqueue.py:enqueue_delivery`, sostituibile nei test con un raccoglitore in memoria. | Il rispetto dell'ordine commit-poi-enqueue (spec sezione 8.3) e verificabile con un test unitario, senza broker. |
| **D8** | Le regex utente si eseguono solo tramite `app/services/severity.py`, unico modulo autorizzato a importare `re2`. Un test di lint verifica che `import re` non compaia in nessun modulo che valuta pattern utente. | L'invariante I-3 diventa meccanicamente verificabile invece che affidata alla disciplina. |
| **D9** | Nessun ORM lazy loading: tutte le relazioni sono `lazy="raise"`. Le query caricano esplicitamente cio che serve. | Con sessioni async il lazy loading esplode a runtime in modo non deterministico. Meglio un errore in test. |
| **D10** | Un solo formato di errore: `app/core/errors.py` espone `problem(status, type, title, detail)` e tutti gli handler passano da li. | RFC 7807 uniforme, e il corpo del 404 di ingestion e generato da una costante unica, il che rende l'invariante I-2 dimostrabile. |
| **D11** | Frontend senza framework CSS esterni: un solo `frontend/src/styles.css`. Stato server con TanStack Query, routing con React Router, test con Vitest piu Testing Library piu MSW. | Nessuna configurazione di build fragile da mettere a punto. |
| **D12** | Le fasi 5 (ingestion) e 6 (outbound) sono separate: la fase 5 salva solo la Notification, la fase 6 aggiunge la creazione delle Delivery nella stessa transazione modificando un punto di inserimento nominato esplicitamente. | Entrambe le fasi restano rilasciabili da sole. Il punto di inserimento e citato in 6.4 con il commento sentinella lasciato in fase 5. |

## Architecture summary

FastAPI async per l'API e l'ingestion, tre connection pool distinti mappati sui tre ruoli Postgres di runtime, isolamento affidato a RLS con `SET LOCAL app.tenant_id` per transazione. I payload oltre 1MB finiscono su MinIO e in tabella resta `storage_key` piu `content_preview` di 4096 caratteri, che alimenta lista, ricerca e formattazione outbound. L'inoltro segue il pattern outbox: le righe `deliveries` nascono nella stessa transazione della notifica, il task viene accodato dopo il commit e un job di riconciliazione ogni cinque minuti garantisce la consegna anche se il broker perde messaggi. Celery gira su un engine SQLAlchemy sincrono separato da quello async dell'API.

## Struttura del repository (vincolante)

```
notifyhub-spec.md
plan_NotifyHub/            questo piano
Makefile                   tutti i comandi operativi
docker-compose.yml         stack di esercizio
docker-compose.test.yml    servizi per i test (porte 5433/6380/9002)
.env.example
README.md
backend/
  requirements.txt  requirements-dev.txt  pyproject.toml  alembic.ini
  alembic/env.py  alembic/versions/
  app/
    main.py  cli.py
    core/      config.py logging.py errors.py crypto.py security.py metrics.py
    db/        base.py types.py session.py sync_session.py
    models/    un modulo per aggregato
    schemas/   un modulo per aggregato
    api/       deps.py  v1/<risorsa>.py  ingest.py
    services/  severity.py storage.py ratelimit.py idempotency.py ingest.py
               outbound_resolver.py quota.py
    outbound/  sender.py formatters/slack.py formatters/google_chat.py
    tasks/     celery_app.py enqueue.py delivery.py maintenance.py
  tests/
    conftest.py  unit/  integration/  e2e/
frontend/
  package.json vite.config.ts tsconfig.json
  src/  api/ components/ pages/ hooks/ styles.css main.tsx App.tsx
  tests/
deploy/
  nginx/nginx.conf
  postgres/initdb/00-roles.sql
  api/Dockerfile  frontend/Dockerfile
scripts/
  smoke.sh  mock_webhook.py
```

## Phases

| Fase | File | Modello prevalente | Rilasciabile da sola |
|------|------|--------------------|----------------------|
| 0 — Scaffolding, tooling, catena dei gate | [phase_01.md](phase_01.md) | Haiku | si |
| 1 — Modello dati, migrazioni, RLS | [phase_02.md](phase_02.md) | Sonnet, gate Opus | si |
| 2 — Nucleo trasversale (config, log, errori, cripto, metriche) | [phase_03.md](phase_03.md) | Sonnet | si |
| 3 — Autenticazione e identita | [phase_04.md](phase_04.md) | Sonnet, gate Opus | si |
| 4 — Management di dominio | [phase_05.md](phase_05.md) | Sonnet | si |
| 5 — Ingestion | [phase_06.md](phase_06.md) | Sonnet, gate Opus | si |
| 6 — Outbound e outbox | [phase_07.md](phase_07.md) | Sonnet, gate Opus | si |
| 7 — API di consultazione | [phase_08.md](phase_08.md) | Sonnet | si |
| 8 — Manutenzione, quote, osservabilita | [phase_09.md](phase_09.md) | Sonnet | si |
| 9 — Dashboard React | [phase_10.md](phase_10.md) | Sonnet | si |
| 10 — Deploy, smoke test, documentazione | [phase_11.md](phase_11.md) | Sonnet, gate Opus | si |

## Reuse map

Il repository e vuoto: non esiste codice da riusare e la mappa di riuso in senso classico non e applicabile. Gli anchor autoritativi sono le sezioni della specifica, tutte verificate come esistenti in `notifyhub-spec.md` v0.3 prima della stesura del piano.

| Necessita | Fonte autoritativa | Anchor |
|-----------|--------------------|--------|
| Schema delle tabelle e vincoli | Spec sezione 4 | `notifyhub-spec.md` § 4.1, 4.2, 4.3 |
| Policy RLS, ruoli, meccanica dei pool | Spec sezione 5 | `notifyhub-spec.md` § 5.1, 5.2, 5.3 |
| Contratto dei moduli di ingestion | Spec sezione 6.1 | `notifyhub-spec.md` § 6.1 |
| Normalizzazione del testo in ingresso | Spec sezione 6.2 | `notifyhub-spec.md` § 6.2 |
| Idempotenza su X-Request-Id | Spec sezione 6.3 | `notifyhub-spec.md` § 6.3 |
| Soglia inline/object, chiavi, flussi | Spec sezione 6.5 | `notifyhub-spec.md` § 6.5 |
| Catena di risoluzione della severity | Spec sezione 7 | `notifyhub-spec.md` § 7 |
| Risoluzione destinazioni, outbox, retry | Spec sezione 8 | `notifyhub-spec.md` § 8.1 - 8.5 |
| Superficie API completa e codici | Spec sezione 9 | `notifyhub-spec.md` § 9.1 - 9.5 |
| Requisiti di sicurezza | Spec sezione 10 | `notifyhub-spec.md` § 10.1 - 10.4 |
| Job di manutenzione | Spec sezione 11 | `notifyhub-spec.md` § 11 |
| Servizi e variabili d'ambiente | Spec sezione 13 | `notifyhub-spec.md` § 13 |

## Invariants

Ogni fase successiva deve lasciarli veri. Sono citati per sigla nelle sotto-fasi; non vanno rispiegati.

- **I-1** Nessun ruolo Postgres del sistema ha `BYPASSRLS`. Ogni lettura o scrittura su tabelle con `tenant_id` avviene in una transazione con `app.tenant_id` impostato, oppure tramite i ruoli di sola lettura `notifyhub_ingest` e `notifyhub_auth` limitati alle rispettive tabelle.
- **I-2** L'endpoint `/ingest/{slug}` risponde `404` con corpo byte-identico e tempi indistinguibili nei tre casi: slug inesistente, receiver `disabled`, tenant `suspended`. Non esiste alcun `410` nel sistema.
- **I-3** Nessuna regex fornita da un utente viene eseguita con il modulo `re` della libreria standard. L'unico punto di valutazione e `app/services/severity.py`, che usa `re2`.
- **I-4** Il worker di inoltro non legge mai `notifications.content` ne oggetti da MinIO. Formatta esclusivamente da `content_preview` e `content_size`.
- **I-5** Nessun task Celery viene accodato dentro una transazione aperta. L'accodamento avviene solo dopo il commit.
- **I-6** Nessun segreto compare mai in log, risposte API o path di URL: webhook in chiaro, token di invito, password, refresh token. I webhook si espongono solo come hint mascherato.
- **I-7** L'ingestion non fallisce mai a causa del contenuto: qualunque sequenza di byte viene normalizzata e salvata.
- **I-8** Ogni cancellazione di una riga `notifications` con `storage_backend = 'object'` accoda la `storage_key` in `pending_object_deletions`, per qualunque percorso di cancellazione, incluso il cascade.
- **I-9** Zero regressioni: al termine di ogni sotto-fase tutti i test delle fasi precedenti restano verdi.

## Risk register

| Rischio | Mitigazione |
|---------|-------------|
| La RLS viene aggirata per errore, i tenant si vedono fra loro | Fase 1 sotto-fase 1.10: suite dedicata con test negativi che leggono senza `app.tenant_id` e con il tenant sbagliato. I test girano contro i ruoli reali, non contro il proprietario |
| `google-re2` non installabile sull'ambiente | Fase 0 sotto-fase 0.2 verifica l'import in un test dedicato. Se fallisce, si ferma e si chiede: non esiste ripiego autorizzato su `re` |
| Il pattern outbox parte prima del commit e i task falliscono | Fase 6 sotto-fase 6.5: test unitario sull'ordine di invocazione con enqueuer finto, piu il job di riconciliazione come rete |
| Oggetti orfani su MinIO dopo commit falliti | Fase 8 sotto-fase 8.5: `purge_orphan_objects` con test che crea deliberatamente un orfano e verifica che sparisca |
| Il limite di dimensione non scatta perche nginx bufferizza | Fase 10 sotto-fase 10.1 imposta `proxy_request_buffering off` e lo smoke test invia un corpo oltre il limite verificando il `413` |
| L'implementatore introduce dipendenze o cartelle non previste | Regole vincolanti in testa a questo file, piu il gate di fase 0 che fallisce se `requirements.txt` cambia senza autorizzazione |
| Il frontend diverge dalle risposte reali dell'API | Fase 9 usa MSW con fixture copiate dalle risposte dei test e2e della fase 7, non inventate |

## Comandi dei gate

Tutti i comandi si lanciano dalla radice del repository. I servizi di test devono essere in piedi (`make up-test`).

| Gate | Comando |
|------|---------|
| Formattazione | `make fmt-check` |
| Lint | `make lint` |
| Tipi | `make types` |
| Test backend completi | `make test` |
| Solo unitari | `make test-unit` |
| Solo integrazione | `make test-int` |
| Lint frontend | `make fe-lint` |
| Test frontend | `make fe-test` |
| Build frontend | `make fe-build` |
| Tutti i gate backend | `make gates` |

## Model assignment summary

| Fase | Sonnet | Haiku | Gate di revisione Opus |
|------|--------|-------|------------------------|
| 0 — Scaffolding | 0.3, 0.6, 0.7 | 0.1, 0.2, 0.4, 0.5 | nessuno |
| 1 — Dati e RLS | 1.3, 1.4, 1.5, 1.6, 1.7, 1.9, 1.10 | 1.1, 1.2, 1.8 | 1.8 policy RLS, 1.9 gestione delle sessioni, 1.10 asserzioni della suite RLS |
| 2 — Nucleo | 2.1, 2.2, 2.3, 2.4, 2.6 | 2.5 | 2.3 cifratura |
| 3 — Auth | 3.2, 3.3, 3.4, 3.6, 3.7, 3.8 | 3.1, 3.5 | 3.2 lookup pre-auth, 3.7 vincolo ultimo owner |
| 4 — Management | 4.1, 4.2, 4.3, 4.5 | 4.4 | 4.3 validazione RE2 |
| 5 — Ingestion | 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7 | nessuna | 5.2 uniformita del 404, 5.7 assemblaggio dell'endpoint |
| 6 — Outbound | 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9 | 6.10 | 6.4 transazione outbox, 6.5 ordine commit-enqueue, 6.8 macchina a stati |
| 7 — Consultazione | 7.1, 7.2, 7.3 | 7.4 | 7.1 paginazione a cursore |
| 8 — Manutenzione | 8.2, 8.3, 8.4, 8.5, 8.6 | 8.1, 8.7 | 8.5 cancellazione oggetti |
| 9 — Frontend | 9.2, 9.3, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10 | 9.1, 9.4 | nessuno |
| 10 — Deploy | 10.1, 10.2, 10.3, 10.4 | 10.5 | 10.4 asserzioni dello smoke test, 10.6 lettura finale |
