# NotifyHub

Aggregatore di notifiche multi-tenant self-hosted. Riceve messaggi da fonti esterne su endpoint
identificati da uno slug, li conserva isolati per tenant tramite Row Level Security di PostgreSQL,
li mostra in una dashboard e li inoltra a Slack e Google Chat sopra una soglia di severita.

La specifica funzionale e tecnica completa e in [`notifyhub-spec.md`](notifyhub-spec.md) v0.3 ed e
l'unica fonte di verita. Il piano di realizzazione e in [`plan_NotifyHub/`](plan_NotifyHub/).

## Stato del progetto

**Implementato e verificato.** Tutte le fasi 0-10 del piano sono `DONE`: schema dati e RLS,
autenticazione, gestione di dominio (gruppi/receiver/canali/regole di severity), ingestion
conforme alla spec, inoltro asincrono verso Slack/Google Chat con pattern outbox, job di
manutenzione, dashboard React, deploy Docker Compose. Stato difetto-per-difetto e verifiche
eseguite in [`docs/REVIEW.md`](docs/REVIEW.md) (sezioni "Verifica 2" e "Verifica 3"); stato per fase e famiglia di
test in [`plan_NotifyHub/resume.md`](plan_NotifyHub/resume.md).

| Area | Stato |
|---|---|
| Schema dati, migrazioni 0001-0013, RLS su tutte le tabelle | verificato: `alembic upgrade head` verde nel servizio `migrate` |
| Autenticazione JWT, refresh rotante, inviti, vincolo ultimo owner | presente |
| Gestione gruppi/receiver/canali/severity-rules | presente, path conformi alla spec sezione 9 |
| Preset di regole di severity (catalogo estensibile, editabili in dashboard) | presente: `bash-generic`, `postgres`, `mongodb`, `tar`, `rclone` |
| Ingestion `POST /ingest/{slug}` | presente: normalizzazione UTF-8, idempotenza, rate limit IP+slug, catena di severity con RE2, offload MinIO |
| Inoltro Slack/Google Chat, outbox, worker Celery | presente: verificato con consegna reale al webhook mock |
| Job di manutenzione (8), quote, metriche, `/readyz` | presenti |
| Dashboard React | presente, `frontend/`, build di produzione servita da nginx |

`backend/`: 541 test (0 skippati), `ruff format`/`ruff check`/`mypy` puliti. `frontend/`: 96 test,
lint e build puliti. `scripts/smoke.sh` eseguito per intero contro lo stack di produzione
containerizzato: 22/22 assert, exit 0.

## Requisiti

- Docker e Docker Compose v2
- GNU Make
- Python 3.12 per eseguire la suite di test dall'host
- Node.js 22 per lavorare sul frontend dall'host

## Avvio

```bash
cp .env.example .env
# generare una chiave vera prima di qualunque uso non locale
sed -i "s/^NOTIFYHUB_SECRET_KEY=.*/NOTIFYHUB_SECRET_KEY=$(openssl rand -hex 32)/" .env
make up
```

`docker compose up -d` avvia Postgres, Redis, MinIO, esegue le migrazioni nel servizio one-shot
`migrate`, poi `api`, `worker`, `beat` e `nginx` (che builda ed espone la SPA). Le URL di `.env`
puntano a `localhost` per lo sviluppo fuori container e vengono sovrascritte nel compose con i nomi
dei servizi.

### Porte

| Porta | Servizio | Esposizione |
|---|---|---|
| 80 | nginx, unico ingresso pubblico (SPA + `/api/v1/*` + `/ingest/*`) | host, configurabile con `HTTP_PORT` |
| 9001 | console MinIO | solo `127.0.0.1` |
| 8000 | API | solo rete interna |
| 9100 | `/metrics` | solo rete interna |
| 5432, 6379, 9000 | Postgres, Redis, MinIO | solo rete interna |

### Profili del compose

```bash
docker compose up -d                  # postgres, redis, minio, migrate, api, worker, beat, nginx
docker compose --profile smoke up -d  # aggiunge anche il webhook finto usato da scripts/smoke.sh
```

`worker` e `beat` sono nel profilo di default: non serve alcun flag aggiuntivo per l'inoltro
asincrono e i job di manutenzione.

## Primo tenant

La registrazione pubblica e disabilitata (`ALLOW_PUBLIC_REGISTRATION=false`) e il primo tenant si
crea da CLI:

```bash
docker compose run --rm migrate python -m app.cli bootstrap \
    --tenant-name "ACME" --email admin@acme.it --password <password>
```

`--password` puo essere omesso: viene richiesta in modo interattivo con conferma. Il comando
presuppone `alembic upgrade head` gia eseguito (lo fa il servizio `migrate` all'avvio) e scrive solo
dati, mai schema.

## Invio di una notifica

Contratto della specifica, sezione 6.2 (curl e wget impostano da soli
`Content-Type: application/x-www-form-urlencoded` quando non specificato: e accettato allo stesso
modo di `text/plain`):

```bash
curl --data "Backup completato" https://notifyhub.example.com/ingest/{slug}
curl -H "X-Severity: error" --data "Backup FALLITO" https://.../ingest/{slug}
wget --post-data="messaggio" https://.../ingest/{slug}
```

Per i job periodici c'e `scripts/notifyhub-run.sh`, che esegue un comando, ne invia l'output insieme
agli header `X-Exit-Code` e `X-Duration-Ms` (durata dell'esecuzione) e restituisce comunque l'exit
code originale al chiamante. Che severity dare a un'esecuzione fallita, o a una durata oltre la
soglia configurata sul receiver, lo decide il receiver (default: `critical` sul fallimento, nessuna
soglia di durata), non lo script:

```bash
scripts/notifyhub-run.sh -s {slug} -- /usr/local/bin/backup.sh /dati
```

Lo script non va compilato a mano: nella pagina di ogni receiver il pulsante **Scarica lo script**
restituisce `notifyhub-run.sh` con URL dell'istanza e slug gia dentro, in due variabili in cima al
file che restano modificabili (e che `NOTIFYHUB_URL`/`NOTIFYHUB_SLUG` e le opzioni `-u`/`-s`
scavalcano comunque). L'URL e quella pubblica risolta dal server: con l'istanza dietro reverse proxy
in https si valorizza `NOTIFYHUB_PUBLIC_BASE_URL`, e in mancanza di quella vale l'indirizzo da cui
la dashboard sta rispondendo, `X-Forwarded-Proto` compreso. Lo stesso indirizzo compare come "URL di
invio" nella pagina del receiver, cosi script e dashboard non possono divergere.

Sul receiver si dichiara anche **ogni quanto ci si aspetta un invio** (intervallo
fisso o la stessa espressione cron del crontab, col suo fuso). Se l'invio non
arriva entro la scadenza piu la tolleranza, NotifyHub scrive da se una notifica di
assenza con la severity configurata e la manda sui canali: e il caso che nessuna
regola sul contenuto puo vedere, perche non c'e nessun contenuto. Una sola
notifica per assenza, piu una di ripresa quando il job torna a inviare.

Con `--ping-start` il wrapper annuncia anche l'avvio (`X-Phase: start`): serve a
distinguere "il cron non e partito" da "il job e partito e si e interrotto a
meta", che altrimenti arrivano come lo stesso silenzio.

Come viene decisa la severity di una notifica, come si configurano le regole e
come funziona la sorveglianza dell'attesa:
[`docs/SEVERITY.md`](docs/SEVERITY.md).

I receiver non devono partire da zero: esistono **preset di regole** già pronti
per gli errori di bash, PostgreSQL, MongoDB, `tar` e `rclone`, applicabili anche
in combinazione allo stesso receiver e modificabili dalla dashboard. Un tenant
nuovo li trova installati; per installarli su un'istanza già esistente, o dopo
un aggiornamento che ne aggiunge di nuovi:

```bash
docker compose run --rm migrate python -m app.cli sync-presets
```

## Sviluppo

```bash
make install     # dipendenze Python di sviluppo
make up-test     # Postgres 5433, Redis 6380, MinIO 9002 e 9003, tutti su loopback
make test        # pytest sull'intera suite
make test-unit   # solo i test unitari
make test-int    # solo i test di integrazione
make gates       # fmt-check, lint, types, test
make down-test   # ferma i servizi di test

npm --prefix frontend install
make fe-lint     # eslint
make fe-test     # vitest
make fe-build    # build di produzione
```

I servizi di test usano volumi effimeri: lo stato non sopravvive a un `down-test` e ogni sessione
puo ripartire pulita. I ruoli Postgres vengono creati da `deploy/postgres/initdb/00-roles.sql` alla
prima creazione del container, quindi dopo una modifica ai ruoli serve `make down-test && make up-test`.

Per riprodurre lo scenario di accettazione della spec sezione 12 contro lo stack containerizzato
completo (non contro `httpx.ASGITransport`):

```bash
bash scripts/smoke.sh
```

## Architettura

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

Punti portanti del progetto, descritti per esteso nella specifica:

- **Isolamento**: schema condiviso con `tenant_id` e Row Level Security forzata. Quattro ruoli
  Postgres, nessuno con `BYPASSRLS`. Ogni transazione applicativa imposta `app.tenant_id` con
  `SET LOCAL`; senza quella variabile le policy non restituiscono nulla, il default e il diniego.
- **Ingestion a moduli**: il core riceve un `IngestionResult` e lo persiste, senza conoscere il
  canale di provenienza. In v1 esiste il solo modulo `http_raw`.
- **Payload**: fino a 1 MB in colonna, oltre su MinIO con `storage_key` in tabella e un
  `content_preview` di 4096 caratteri che alimenta lista, ricerca e messaggi di inoltro.
- **Inoltro**: pattern outbox. Le righe `deliveries` nascono nella stessa transazione della
  notifica, il task Celery viene accodato dopo il commit e un job di riconciliazione ogni cinque
  minuti recupera quello che il broker perde.
- **Regex utente**: valutate con `google-re2`, tempo lineare, ReDoS strutturalmente impossibile.

## Struttura del repository

```
notifyhub-spec.md          specifica funzionale e tecnica, fonte di verita
plan_NotifyHub/            piano di realizzazione per fasi e stato di avanzamento
docs/REVIEW.md             revisioni di accettazione
docs/OPERAZIONI.md         procedure operative: job, metriche, backup, troubleshooting
docs/SEVERITY.md           guida alla configurazione delle severity e delle regole
Makefile                   comandi di sviluppo e di esercizio
docker-compose.yml         stack di esercizio
docker-compose.test.yml    servizi reali per i test
backend/                   API FastAPI, modelli, migrazioni Alembic, test
frontend/                  dashboard React, Vite, test
deploy/                    Dockerfile, configurazione nginx, init di Postgres
scripts/                   wrapper di invio, smoke test e webhook finto
```

## Sicurezza

- Slug `gruppo-receiver-token`: il prefisso e leggibile, la credenziale e il token di 22 caratteri
  in coda, 128 bit di entropia. Rinominare non riscrive lo slug (gli script in produzione
  continuerebbero a inviare a un indirizzo morto): lo riallinea `rotate-slug`, ad admin+.
- Risposta `404` uniforme per slug inesistente, receiver disabilitato e tenant sospeso: nessun
  oracolo di enumerazione.
- Password con Argon2id, access token di 15 minuti, refresh token rotanti con rilevamento del
  riuso e famiglia per catena di rotazione.
- `webhook_url` cifrato a riposo con AES-GCM e mai restituito in chiaro dall'API.
- `/metrics` e la console MinIO non sono instradati da nginx.

Cambiare le password di default prima di esporre l'istanza a una rete non fidata: vedi
`docs/OPERAZIONI.md` sezione "Messa in Produzione".

## Licenza

Da definire.
