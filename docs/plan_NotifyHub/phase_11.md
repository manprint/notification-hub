# Fase 10 — Deploy, smoke test di accettazione, documentazione

> **Intent:** mettere in piedi lo stack completo dietro nginx e dimostrare, con un unico comando, che lo scenario di riferimento dell'overview funziona davvero.
> **Shippable alone?** si — e la fase che rende il prodotto installabile da terzi.
> **Preconditions:** fase 9 DONE.

Fonti autoritative: `notifyhub-spec.md` sezione 13 (servizi ed env), sezione 10.1 (limiti e buffering di nginx), sezione 10.4 (superficie esposta), sezione 12 (scenario end-to-end).

---

## Sub-phases

### 10.1 Configurazione di nginx

- **Model:** Sonnet
- **Files:** `deploy/nginx/nginx.conf` (nuovo).
- **Change:** un solo `server` block sulla porta 80 (la terminazione TLS e a carico di chi installa e va documentata, non simulata). Instrada **solo** le rotte previste dalla specifica sezione 10.4:

  | Location | Destinazione | Direttive obbligatorie |
  |----------|--------------|------------------------|
  | `/` | file statici della SPA | `try_files $uri /index.html` per il routing lato client |
  | `/api/v1/` | `api:8000` | `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`, `X-Forwarded-Proto`, `Host` |
  | `/ingest/` | `api:8000` | le stesse intestazioni, piu **`proxy_request_buffering off`** e `client_max_body_size 20m` |
  | `/healthz`, `/readyz` | `api:8000` | — |

  **`/metrics` non e instradato.** Se compare nella configurazione, e un errore: le metriche stanno sulla porta interna 9100 (specifica sezione 10.4).
  `client_max_body_size 20m` a livello di `http`, cosi vale come rete di sicurezza ovunque.

  Il motivo di `proxy_request_buffering off` va scritto come commento nel file: senza, nginx accumula i 20MB su disco prima di inoltrarli e il limite per receiver dell'applicazione non puo piu interrompere la lettura in anticipo (specifica sezione 10.1).
- **Unit tests:** nessuno.
- **e2e tests:** verificati da 10.4.
- **Done:** `docker compose config` non segnala errori; `nginx -t` dentro il container esce con codice 0.

### 10.2 Immagini applicative

- **Model:** Sonnet
- **Files:** `deploy/api/Dockerfile` (nuovo), `deploy/frontend/Dockerfile` (nuovo), `.dockerignore` (nuovo).
- **Change:**
  - `deploy/api/Dockerfile`: base `python:3.12-slim`, installazione di `requirements.txt`, copia di `backend/`, utente non root, `WORKDIR /app`. Nessun `CMD` fisso: il comando lo definisce il compose, perche la stessa immagine serve ad `api`, `worker`, `beat` e `migrate`.
  - `deploy/frontend/Dockerfile`: stadio di build su `node:22-alpine` che esegue `npm ci` e `npm run build`, e stadio finale che copia `dist/` dentro un'immagine `nginx:alpine` insieme a `deploy/nginx/nginx.conf`.
  - `.dockerignore`: `node_modules`, `.git`, `__pycache__`, `.venv`, `frontend/dist`, `*.md` esclusa la documentazione necessaria.
- **Unit tests:** nessuno.
- **e2e tests:** nessuno.
- **Done:** `docker compose build` completa senza errori e `docker run --rm <api-image> python -c "import app.main"` esce con codice 0.

### 10.3 Compose completo

- **Model:** Sonnet
- **Files:** `docker-compose.yml` (modificato).
- **Insertion point:** ai quattro servizi di infrastruttura creati in fase 0 sotto-fase 0.3 si aggiungono i cinque applicativi. Non modificare i servizi esistenti se non per aggiungere le dipendenze.
- **Change:** aggiungi:
  - `migrate` — immagine dell'api, comando `alembic upgrade head`, `depends_on: postgres: service_healthy`, `restart: "no"`. Deve terminare con exit 0 prima che `api` parta.
  - `api` — comando che avvia **due** processi uvicorn: quello applicativo su `0.0.0.0:8000` e quello delle metriche su `0.0.0.0:9100`. Realizzalo con uno script `deploy/api/entrypoint.sh` che avvia il secondo in background e il primo in primo piano; niente supervisore, niente dipendenze nuove. La porta 9100 **non** va pubblicata sull'host in produzione: resta interna alla rete di compose. `depends_on` su `migrate` completato, `redis` e `minio` sani.
  - `worker` — stessa immagine, comando `celery -A app.tasks.celery_app worker -Q delivery --concurrency 4 --loglevel INFO`.
  - `beat` — stessa immagine, comando `celery -A app.tasks.celery_app beat --loglevel INFO`.
  - `nginx` — immagine costruita da `deploy/frontend/Dockerfile`, porta `80:80`, `depends_on: api`.
  - `mock-webhook` — servizio di prova sotto **profilo `smoke`**, cosi `docker compose up -d` normale non lo avvia. Immagine `python:3.12-slim`, esegue `scripts/mock_webhook.py`, porta interna 8899.
  Tutti i servizi applicativi leggono `env_file: .env`.
  Healthcheck su `api`: `curl -f http://localhost:8000/readyz`.
- **Unit tests:** nessuno.
- **e2e tests:** verificati da 10.4.
- **Done:** `docker compose up -d` porta tutti i servizi in stato healthy o completed; `curl -f http://localhost/healthz` risponde 200 passando da nginx; `curl -f http://localhost/metrics` risponde **404**, perche le metriche non sono instradate.

### 10.4 Smoke test di accettazione

- **Model:** Opus design review sulle asserzioni -> Sonnet implementa
- **Files:** `scripts/mock_webhook.py` (nuovo), `scripts/smoke.sh` (nuovo).
- **Pattern:** script bash con `set -euo pipefail`, ogni passo con una asserzione esplicita e un messaggio di fallimento leggibile. Nessuna dipendenza oltre a `curl` e `jq`.
- **Change:**
  - `scripts/mock_webhook.py` — server HTTP della libreria standard, porta 8899. Accetta `POST /hook` registrando corpo e intestazioni in una lista in memoria; espone `GET /_received` che restituisce il JSON delle richieste ricevute e `POST /_reset` che azzera. Nessuna dipendenza esterna.
  - `scripts/smoke.sh` esegue, nell'ordine, i diciassette passi dello scenario di riferimento riportato in `plan_NotifyHub/overview.md`, con queste asserzioni:

    | # | Passo | Asserzione bloccante |
    |---|-------|----------------------|
    | 1 | `docker compose --profile smoke up -d` e attesa di `readyz` | tutti i servizi rispondono entro 90 secondi |
    | 2 | bootstrap del tenant tramite `docker compose run` | exit 0, password catturata |
    | 3 | login | HTTP 200, `access_token` non vuoto |
    | 4 | creazione gruppo | HTTP 201 |
    | 5 | creazione receiver | HTTP 201, `length(slug) == 22` |
    | 6 | creazione canale verso `http://mock-webhook:8899/hook` | HTTP 201, la risposta **non** contiene la stringa `8899/hook` in chiaro ma solo `webhook_hint`. Richiede che `NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST` includa `mock-webhook`: lo script lo imposta solo per la durata dello smoke test, il valore predefinito di `.env.example` resta ai due host ufficiali |
    | 7 | binding gruppo-canale con `min_severity=error` | HTTP 201 |
    | 8 | regola di severity `FALL(ITO\|IMENT)\|ERROR` verso `error` | HTTP 201 |
    | 9 | ingestion con `X-Request-Id: smoke-1` | HTTP 201, `severity == "error"`, `severity_source == "rule"`, `forwarded_to == 1` |
    | 10 | ripetizione identica | HTTP 200 e header `Idempotent-Replay: true` |
    | 11 | ingestion su slug inesistente | HTTP 404, corpo salvato per il confronto |
    | 12 | disabilitazione del receiver e nuova ingestion | HTTP 404 con corpo **byte-identico** a quello del passo 11 |
    | 13 | riabilitazione del receiver | HTTP 200 |
    | 14 | ingestion di un payload da 2MB generato al volo | HTTP 201; il dettaglio riporta `storage_backend == "object"` |
    | 15 | scaricamento del contenuto | il file scaricato ha lo stesso SHA-256 di quello inviato |
    | 16 | attesa fino a 30 secondi e lettura di `GET /_received` sul mock | esattamente **una** richiesta ricevuta, il cui corpo contiene il nome del receiver e il link alla dashboard |
    | 17 | ingestion di un corpo oltre il limite del receiver | HTTP 413 |

    Ogni asserzione fallita stampa il numero del passo, il valore atteso e quello ottenuto, e termina con exit 1. In coda, lo script stampa `SMOKE OK` ed esce con 0.
  - Il passo 12 e la verifica end-to-end dell'invariante I-2; il passo 15 dell'offload; il passo 16 dell'intera catena outbox.
- **Unit tests:** nessuno.
- **e2e tests:** `T-E2E1` — l'esecuzione di `scripts/smoke.sh` su uno stack ricreato da zero (`make reset-db`) termina con exit 0.
- **Done:** `bash scripts/smoke.sh` esce con 0 due volte di seguito su stack pulito, e esce con 1 se si spegne il servizio `worker` prima del passo 16, dimostrando che il passo 16 verifica davvero qualcosa.

### 10.5 Documentazione

- **Model:** Haiku
- **Files:** `README.md` (modificato), `docs/OPERAZIONI.md` (nuovo).

  > **Nota sulla struttura.** `docs/` e la seconda e ultima cartella nuova ammessa oltre all'albero dell'overview, e ospita la sola documentazione operativa. Non creare altre cartelle.
- **Change:**
  - `README.md`: cos'e NotifyHub in cinque righe, requisiti, avvio rapido (`cp .env.example .env`, `make up`, `make migrate`, bootstrap, accesso), come inviare la prima notifica con `curl`, come lanciare i test, come lanciare lo smoke test. Nessuna emoji, nessuna sezione decorativa.
  - `docs/OPERAZIONI.md`: cambio delle password predefinite dei quattro ruoli Postgres e di MinIO **prima** di esporre l'istanza; terminazione TLS davanti a nginx; significato delle variabili d'ambiente, una tabella; i sette job di manutenzione con la loro pianificazione e cosa succede se non girano; procedura di ripristino del database e del bucket, con la precisazione che i due backup vanno presi insieme perche le notifiche offloaded sono metadati in Postgres e byte su MinIO; cosa fare quando `pending_object_deletions_backlog` cresce; come leggere le metriche esposte.
- **Unit tests:** nessuno.
- **e2e tests:** nessuno.
- **Done:** un lettore che non conosce il progetto riesce, seguendo solo il README, ad arrivare alla prima notifica visibile in dashboard.

### 10.6 Lettura finale e accettazione

- **Model:** Opus
- **Files:** nessuno modificato salvo correzioni emerse.
- **Change:** revisione conclusiva, con verifica puntuale dei nove invarianti dell'overview:

  | Invariante | Come si verifica |
  |------------|------------------|
  | I-1 | `T-RLS2` verde; ricerca di `BYPASSRLS` nei sorgenti e nelle migrazioni: nessuna occorrenza |
  | I-2 | `T-ING4`, `T-ING6` verdi e passo 12 dello smoke test |
  | I-3 | `test_nessun_uso_del_modulo_re` verde |
  | I-4 | `T-OUT20` verde e `NotificationSummary` privo dei campi del corpo |
  | I-5 | `T-OUT12` verde con la verifica di autenticita eseguita |
  | I-6 | `T-OUT1`, `T-OUT2`, `T-OUT21`, `T-AUTH20`, `T-UI15` verdi; ricerca di `webhook_url` nei log di uno smoke test completo: nessuna occorrenza in chiaro |
  | I-7 | `T-ING16`, `T-ING24` verdi |
  | I-8 | `T-CONS17`, `T-MAINT4`, `T-DDL3` verdi |
  | I-9 | `make gates` e `make fe-test` verdi sull'intera suite |

  Verifica inoltre che il numero complessivo di test corrisponda alla somma dei `T-*` dichiarati nelle fasi, e che nessun test sia stato disattivato con `skip` o `xfail` senza una motivazione scritta.
- **Unit tests:** nessuno.
- **e2e tests:** l'intera suite, piu `T-E2E1`.
- **Done:** tutte le righe della tabella verificate; `resume.md` aggiornato con tutte le fasi `DONE`.

---

## Files touched (this phase)

- `deploy/nginx/nginx.conf` — creato — instradamento, limiti, buffering disattivato su `/ingest/`
- `deploy/api/Dockerfile`, `deploy/api/entrypoint.sh` — creati — immagine applicativa e doppio processo uvicorn
- `deploy/frontend/Dockerfile` — creato — build della SPA e immagine nginx
- `.dockerignore` — creato
- `docker-compose.yml` — modificato — cinque servizi applicativi e il mock sotto profilo
- `scripts/mock_webhook.py` — creato — ricevitore di prova per lo smoke test
- `scripts/smoke.sh` — creato — accettazione end-to-end in diciassette passi
- `README.md` — modificato — avvio rapido
- `docs/OPERAZIONI.md` — creato — esercizio, backup, manutenzione

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint` e `make fe-lint`
- **Tipi:** `make types`
- **Test:** `make test` e `make fe-test`
- **Accettazione:** `bash scripts/smoke.sh` su stack ricreato da zero
- **Regression guard:** l'intera suite `T-*` delle fasi 0-9.

## Phase done criterion

Su una macchina pulita: `cp .env.example .env && make up && bash scripts/smoke.sh` stampa `SMOKE OK` ed esce con 0. La tabella degli invarianti della sotto-fase 10.6 e verificata riga per riga. `resume.md` riporta tutte le fasi `DONE` e nessun blocco aperto.
