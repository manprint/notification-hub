# NotifyHub all-in-one

Tutto lo stack di produzione in un solo container: PostgreSQL, Redis, MinIO, API FastAPI, worker
Celery, beat Celery e nginx con la SPA React gia' buildata. Un solo volume per i dati, un solo
volume per i log, un healthcheck che dice se l'applicazione e' davvero servibile.

Serve per installazioni self-hosted piccole, demo e ambienti dove non si vuole gestire uno stack
Compose. Per sviluppo e per installazioni con componenti separate resta valido il
`docker-compose.yml` in radice.

## Contenuto dell'immagine

| Componente | Versione | Note |
|---|---|---|
| Debian | 13 "trixie" | base `python:3.12-slim-trixie`, che e' Debian 13 con Python 3.12 in `/usr/local` |
| PostgreSQL | 17 (pacchetto Debian) | cluster in `/data/postgres`, in ascolto solo su `127.0.0.1` |
| Redis | 8 (pacchetto Debian) | broker Celery, rate limit, idempotenza; AOF in `/data/redis` |
| MinIO | RELEASE.2025-09-07 | storage S3 dei payload in `/data/minio`, piu' il client `mc` |
| Python | 3.12 | la versione su cui il backend e' sviluppato e testato |
| nginx | 1.26 | unico ingresso pubblico, porta 80 |
| supervisord | 4.3.0 | orchestrazione dei processi interni |

Perche' supervisord e non s6-overlay: e' un solo processo Python, gia' presente nel virtualenv
dell'applicazione, e soprattutto espone uno stato interrogabile (`supervisorctl status`) che
l'healthcheck usa per sapere se ogni servizio e' in `RUNNING`. s6 avrebbe richiesto un altro strato
di init e un albero di script per lo stesso risultato.

## Build

Sempre dal Makefile in radice del progetto:

```bash
make all-in-one-build                          # tag 1.0.0 + latest
make all-in-one-build ALL_IN_ONE_VERSION=1.1.0 # tag 1.1.0 + latest
```

La versione finisce in `/opt/notifyhub/VERSION` dentro l'immagine ed e' quella che il container
confronta con `/data/state/version` per decidere se sta facendo un aggiornamento.

## Avvio

```bash
cd deploy/all-in-one
cp .env.example .env       # opzionale: senza, i segreti vengono generati
docker compose -f docker-compose.all-in-one.yml up -d
```

oppure, dalla radice:

```bash
make all-in-one-up      # crea .env dall'esempio se manca
make all-in-one-logs
make all-in-one-health
```

Al primo avvio il container esegue, in quest'ordine e prima di far partire qualunque servizio:

1. creazione del layout in `/data` e `/logs`;
2. generazione dei segreti mancanti in `/data/config/secrets.env`;
3. `initdb` del cluster PostgreSQL, `pg_hba.conf` e tuning;
4. creazione dei ruoli `notifyhub_owner|app|auth|ingest` e del database;
5. `alembic upgrade head`;
6. hook di aggiornamento, allineamento dei preset di severity;
7. creazione del bucket MinIO;
8. `exec supervisord`.

Il primo avvio richiede in genere 40-90 secondi: fino a quel momento l'healthcheck e' `starting`.

### Primo utente

Con `ALLOW_PUBLIC_REGISTRATION=false` (default) la registrazione dal web e' chiusa. Due strade:

```bash
# a) automatica: nel .env prima del primo avvio
NOTIFYHUB_BOOTSTRAP_EMAIL=admin@example.com
NOTIFYHUB_BOOTSTRAP_PASSWORD=              # vuota = generata in /data/config/bootstrap-credentials.txt

# b) manuale, a container avviato
docker compose exec -it notifyhub notifyhub-cli bootstrap
```

`notifyhub-cli` e' la CLI dell'applicazione: `docker exec` parte con le sole variabili
dell'immagine, non con quelle che l'entrypoint esporta per i servizi, e questo wrapper rilegge i
segreti persistiti e ricompone l'ambiente prima di eseguire il comando (`bootstrap`,
`sync-presets`, `--help`).

## Porte

| Porta | Servizio | Esposizione |
|---|---|---|
| 80 | nginx: SPA, `/api/v1/*`, `/ingest/*`, `/healthz`, `/readyz` | pubblicata sull'host (`HTTP_PORT`) |
| 8000 | API uvicorn | solo dentro al container |
| 9100 | `/metrics` Prometheus | `127.0.0.1` nel container; per esporla, `METRICS_BIND=0.0.0.0` e pubblicare la porta |
| 9000 | API S3 di MinIO | `127.0.0.1` nel container; per esporla, `MINIO_BIND=0.0.0.0` e pubblicare la porta |
| 5432 / 6379 | PostgreSQL e Redis | mai raggiungibili da fuori dal container |

nginx non instrada `/metrics`: come nello stack Compose, le metriche restano su una porta separata.

## Persistenza: un solo volume `/data`

```
/data
├── postgres/    cluster PostgreSQL (PGDATA)
├── redis/       AOF e RDB
├── minio/       oggetti S3 (payload delle notifiche)
├── config/      secrets.env, overrides.env, postgresql.custom.conf, upgrade.d/
├── state/       versione installata, major PostgreSQL, schedule di Celery beat
└── backups/     dump pre-aggiornamento e manuali
```

Montare `/data` e' sufficiente a rendere l'installazione persistente e ricreabile: cancellare il
container e ricrearlo sullo stesso volume riporta lo stesso identico stato.

`/data/config/secrets.env` contiene le password dei ruoli PostgreSQL e le chiavi MinIO generate
automaticamente: e' `0600` ed e' il file da salvare insieme al volume.

Due file opzionali che l'operatore puo' creare:

- `/data/config/overrides.env` — variabili d'ambiente aggiuntive, caricate dopo i segreti;
- `/data/config/postgresql.custom.conf` — direttive PostgreSQL incluse per ultime, vincono su tutto.

## Log: un solo volume `/logs`

Ogni servizio ha la sua sottocartella e il suo file, nel formato originale del servizio:

```
/logs
├── init/       entrypoint: inizializzazione, migrazioni, aggiornamenti
├── postgres/   postgres.log
├── redis/      redis.log
├── minio/      minio.log
├── api/        api.log        (structlog JSON dell'applicazione)
├── metrics/    metrics.log
├── worker/     worker.log
├── beat/       beat.log
├── nginx/      nginx.log      (access log in formato combined + error log)
└── supervisor/ supervisord.log
```

La rotazione e' per dimensione: `LOG_MAX_BYTES` (default 10 MB) e `LOG_BACKUPS` (default 5).

Contemporaneamente tutto passa su stdout con il prefisso del servizio, quindi

```bash
docker logs -f notifyhub
```

mostra un unico flusso ordinato nel tempo:

```
[init] - 2026-08-03T18:02:11Z INFO alembic upgrade head
[postgres] - 2026-08-03 18:02:14.882 UTC [142] LOG:  database system is ready to accept connections
[redis] - 142:M 03 Aug 2026 18:02:14.901 * Ready to accept connections tcp
[api] - {"event": "application_startup", "level": "info", "timestamp": "2026-08-03T18:02:20.114Z"}
[nginx] - 172.18.0.1 - - [03/Aug/2026:18:02:31 +0000] "GET /api/v1/notifications HTTP/1.1" 200 1841 "-" "Mozilla/5.0"
[worker] - [2026-08-03 18:02:22,003: INFO/MainProcess] celery@notifyhub ready.
```

Per un solo servizio: `docker logs -f notifyhub | grep '^\[worker\]'` oppure
`docker compose exec notifyhub tail -f /logs/worker/worker.log`.

## Healthcheck

`docker inspect --format '{{.State.Health.Status}}' notifyhub`, oppure `make all-in-one-health` per
vedere il dettaglio. Il container e' `healthy` solo se **tutti** questi controlli passano:

1. supervisord risponde e ha tutti i programmi in `RUNNING`;
2. `pg_isready` sul cluster;
3. `PING` a Redis;
4. `/minio/health/live` su MinIO;
5. `GET /readyz` dell'API restituisce 200 **e** ha `postgres`, `redis`, `minio` tutti a `true`;
6. `/metrics` risponde;
7. nginx serve la SPA e instrada `/healthz`;
8. almeno un worker Celery risponde al ping sul broker.

Uscita tipica:

```
[health] - 2026-08-03T18:05:02Z OK supervisor=ok postgres=ok redis=ok minio=ok api=ok metrics=ok nginx=ok worker=ok
```

Al primo controllo fallito l'healthcheck esce con 1 e stampa il motivo, che resta visibile in
`docker inspect` sotto `State.Health.Log`.

## Smoke test end-to-end

```bash
make all-in-one-smoke
```

`smoke-all-in-one.sh` e' la versione per il container unico di `scripts/smoke.sh` (che verifica lo
stack Compose): stesse asserzioni, stesso ordine. Avvia su una rete dedicata il container
all-in-one e il mock del webhook, attende l'healthcheck, poi verifica bootstrap, login, gruppo,
receiver (slug parlante con token di 22 caratteri e download dello script wrapper precompilato),
canale con webhook mascherata, regola di severity, ingestion con
match della regola, idempotenza con header `Idempotent-Replay`, 404 identico byte a byte fra slug
inesistente e receiver disabilitato (invariante I-2), payload da 2MB su MinIO con download
identico all'originale, consegna reale del webhook esattamente una volta, rifiuto 413 oltre il
limite del receiver. Alla fine rimuove container, volumi e rete.

Variabili utili: `SMOKE_PORT` (default 18099), `SMOKE_MOCK_PORT` (18899), `SMOKE_IMAGE`, e
`--keep` per lasciare in piedi lo stack e ispezionarlo.

## Aggiornamenti

L'aggiornamento e' "cambia il tag dell'immagine e riavvia", sullo stesso volume `/data`:

```bash
make all-in-one-build ALL_IN_ONE_VERSION=1.1.0
make all-in-one-up ALL_IN_ONE_VERSION=1.1.0
```

Cosa fa il container quando trova in `/data/state/version` una versione diversa dalla propria:

1. **backup automatico** — `pg_dumpall` compresso in `/data/backups/notifyhub-pre-<nuova>-<data>.sql.gz`,
   con a fianco l'archivio della configurazione e un manifest. Se il backup fallisce, l'avvio si
   ferma: meglio non partire che migrare senza rete. Disattivabile con
   `NOTIFYHUB_BACKUP_ON_UPGRADE=false`, si tengono gli ultimi `NOTIFYHUB_BACKUP_KEEP` (5).
2. **migrazioni** — `alembic upgrade head` con il cluster avviato ma **prima** che supervisord
   faccia partire API, worker e beat. Nessun processo applicativo puo' quindi vedere uno schema a
   meta'. Se le migrazioni falliscono, il container esce e i servizi non partono.
3. **hook di versione** — gli `*.sh` in `/etc/notifyhub/upgrade.d/` (immagine) e in
   `/data/config/upgrade.d/` (operatore), con `NOTIFYHUB_FROM_VERSION` e `NOTIFYHUB_TO_VERSION`
   nell'ambiente. Servono agli aggiornamenti dati che non stanno in una migrazione di schema.
4. **allineamento dati** — `python -m app sync-presets`, additivo e idempotente: installa nei
   tenant esistenti i preset di severity aggiunti al catalogo dalla nuova versione, senza toccare
   quelli gia' presenti o modificati.
5. **stato** — solo a questo punto `/data/state/version` viene riscritto.

Passare da 1.0.0 a 1.1.0 o direttamente da 1.0.0 a 2.0.0 e' la stessa procedura: le migrazioni
Alembic vengono applicate in sequenza a partire dalla revisione registrata nel database.

**Downgrade**: bloccato. Se `/data/state/version` e' piu' recente della versione dell'immagine il
container si rifiuta di partire, perche' uno schema piu' nuovo puo' contenere oggetti che il codice
piu' vecchio non conosce. Per forzarlo, dopo aver ripristinato un backup coerente:
`ALLOW_DOWNGRADE=true`.

**Major di PostgreSQL**: l'immagine e' pinnata su PostgreSQL 17 e il cluster in `/data/postgres`
resta compatibile per tutta la vita di questa base. Se una futura immagine cambiasse major, il
container si ferma prima di toccare i dati e stampa la procedura (backup con la vecchia immagine,
cluster nuovo, `notifyhub-restore`).

## Backup e ripristino

```bash
# dump manuale (database + configurazione) in /data/backups
docker compose exec notifyhub notifyhub-backup --label prima-della-modifica
make all-in-one-backup

# elenco
docker compose exec notifyhub ls -lh /data/backups

# ripristino: distruttivo, chiede conferma
docker compose exec notifyhub notifyhub-restore /data/backups/notifyhub-manual-20260803T180000Z.sql.gz
```

Il dump non contiene gli oggetti MinIO: stanno nello stesso volume `/data` e per una copia completa
conviene fare lo snapshot del volume a container fermo.

## Comandi utili

```bash
make all-in-one-ps                # stato del container
make all-in-one-shell             # shell dentro al container
make all-in-one-restart
make all-in-one-clean CONFIRM=yes # elimina i volumi: database, oggetti, configurazione, log

docker compose exec -it notifyhub notifyhub-cli bootstrap   # CLI applicativa
docker compose exec notifyhub notifyhub-ctl status          # stato dei singoli servizi
docker compose exec notifyhub notifyhub-ctl restart worker  # riavvio di un solo servizio
docker compose exec notifyhub notifyhub-ctl tail -f api
docker compose exec notifyhub psql -U postgres notifyhub    # via socket locale
docker compose exec notifyhub mc ls local/notifyhub-payloads
```

## Configurazione

Tutte le variabili sono documentate in [`.env.example`](.env.example). Le piu' rilevanti:

| Variabile | Default | Effetto |
|---|---|---|
| `HTTP_PORT` | `80` | porta pubblicata sull'host |
| `NOTIFYHUB_PUBLIC_BASE_URL` | `http://localhost` | URL pubblica: inviti, link delle notifiche, URL di ingestion in dashboard e script wrapper scaricabile. Se resta loopback, le risposte HTTP la deducono da `Host` e `X-Forwarded-Proto`; il worker Celery usa comunque questo valore |
| `NOTIFYHUB_SECRET_KEY` | generata | firma dei token; cambiarla invalida le sessioni |
| `NOTIFYHUB_BOOTSTRAP_EMAIL` | vuota | crea il primo tenant al primo avvio |
| `UVICORN_WORKERS` / `WORKER_CONCURRENCY` | `2` / `4` | dimensionamento API e worker |
| `PG_SHARED_BUFFERS`, `PG_MAX_CONNECTIONS`, ... | vedi esempio | tuning PostgreSQL |
| `METRICS_BIND` / `MINIO_BIND` | `127.0.0.1` | mettere `0.0.0.0` per esporre le rispettive porte |
| `LOG_MAX_BYTES` / `LOG_BACKUPS` | `10485760` / `5` | rotazione dei file in `/logs` |
| `ALLOW_DOWNGRADE` | `false` | consente di avviare una versione piu' vecchia dei dati |

I segreti valorizzati nell'ambiente hanno la precedenza su quelli persistiti: le password dei ruoli
PostgreSQL vengono riallineate a ogni avvio, quindi cambiarle e' sicuro e non richiede interventi
manuali sul database.

## Sicurezza

- L'unica porta pubblicata e' la 80 di nginx. PostgreSQL, Redis, MinIO e l'API ascoltano solo su
  loopback dentro al container.
- Nessun servizio applicativo gira da root: API, worker, beat, Redis, MinIO e i worker nginx
  girano come `notifyhub` (uid 1000), PostgreSQL come `postgres`. Restano root solo l'entrypoint,
  supervisord e il master nginx (per la porta 80).
- I segreti generati stanno in `/data/config/secrets.env` con permessi `0600`, mai nell'immagine.
- HTTPS non e' incluso: davanti al container va messo un reverse proxy con i certificati, e in quel
  caso vanno valorizzate `TRUSTED_PROXIES` e `NOTIFYHUB_PUBLIC_BASE_URL`.

## Diagnostica

| Sintomo | Dove guardare |
|---|---|
| container `unhealthy` | `docker inspect --format '{{json .State.Health}}' notifyhub`, poi `notifyhub-ctl status` |
| resta in `starting` a lungo | `docker logs notifyhub | grep '^\[init\]'`: initdb e migrazioni sono li' |
| l'avvio si ferma sulle migrazioni | `/logs/init/init.log`, il container esce apposta per non partire con schema incoerente |
| 502 da nginx | l'API non e' su :8000, vedere `[api]` nei log |
| `/readyz` con `minio: false` | bucket o credenziali: `[minio]` nei log e `mc ls local/` |
| consegne ferme | `[worker]` e `[beat]` nei log; `notifyhub-ctl restart worker` |
