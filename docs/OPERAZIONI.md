# Guida Operativa NotifyHub

## Messa in Produzione

### Cambio Password Predefinite

Prima di esporre NotifyHub su Internet, cambia le password di default dei quattro ruoli PostgreSQL
(`deploy/postgres/initdb/00-roles.sql`, applicato solo al primo avvio del volume) e dell'accesso
MinIO.

#### PostgreSQL

```bash
openssl rand -base64 32   # ripeti per ciascuna delle quattro password

# deploy/postgres/initdb/00-roles.sql (prima del primo avvio, il file gira una sola volta
# per volume): sostituisci le quattro password dev_owner/dev_app/dev_auth/dev_ingest.

# .env: aggiorna le URL con le stesse password
PG_OWNER_PASSWORD=<nuova_password_owner>
PG_APP_PASSWORD=<nuova_password_app>
PG_AUTH_PASSWORD=<nuova_password_auth>
PG_INGEST_PASSWORD=<nuova_password_ingest>
```

Un cambio password su un volume Postgres gia inizializzato richiede `make reset-db` (o
`ALTER ROLE ... PASSWORD` manuale): `00-roles.sql` non viene rieseguito su un volume esistente.

#### MinIO

```bash
# .env
NOTIFYHUB_S3_ACCESS_KEY=<nuovo_access_key>
NOTIFYHUB_S3_SECRET_KEY=<nuovo_secret_key>
```

```bash
docker compose down
docker compose up -d minio minio-init   # minio-init ricrea il bucket con le nuove credenziali
```

### Terminazione TLS

`nginx` ascolta sulla porta 80 senza TLS (`deploy/nginx/nginx.conf`). Per la produzione:

1. Procurati un certificato (Let's Encrypt, self-signed, o terminazione a monte).
2. Aggiungi un server block `listen 443 ssl` con `ssl_certificate`/`ssl_certificate_key` e un
   redirect 301 dal blocco `listen 80` esistente.
3. Monta i certificati nel container `nginx` via `volumes` in `docker-compose.yml`.

### URL pubblica dietro reverse proxy

Tutto quello che l'istanza mette in mano a qualcun altro contiene un indirizzo: il link dell'invito,
il link della notifica inoltrata su Slack, l'URL di ingestion mostrata nella pagina del receiver e lo
script `notifyhub-run.sh` che si scarica da quella pagina. Un indirizzo sbagliato non da errore: da
un link che non risponde, o che risponde solo dalla macchina dell'API.

Ordine con cui viene deciso (`backend/app/core/urls.py`):

1. **`NOTIFYHUB_PUBLIC_BASE_URL`**, se non punta al loopback. E la dichiarazione dell'operatore ed e
   la sola cosa da valorizzare in produzione: `https://notifyhub.example.com`, con l'eventuale
   sottopercorso e senza slash finale (viene comunque normalizzata).
2. **La richiesta in corso**, quando c'e: `X-Forwarded-Proto`, `X-Forwarded-Host` e
   `X-Forwarded-Prefix` se il proxy li manda, altrimenti schema e header `Host`. Copre il caso reale
   in cui la configurazione e rimasta al default di sviluppo dopo il deploy dietro nginx in https.
3. La configurazione comunque, anche loopback, come ultima spiaggia.

Il **worker Celery** non ha nessuna richiesta da cui dedurla: i link nelle notifiche inoltrate usano
solo il punto 1. Se arrivano su Slack link a `localhost`, la variabile non e valorizzata.

`nginx` di questo repository manda gia `Host` e `X-Forwarded-Proto` (`deploy/nginx/nginx.conf`); un
proxy davanti a quello deve fare lo stesso, e se serve l'istanza sotto un sottopercorso deve mandare
anche `X-Forwarded-Prefix`. Il valore viene sempre validato: credenziali nell'URL, query string,
spazi e caratteri fuori dall'alfabeto degli URL vengono rifiutati, perche la stessa stringa finisce
dentro uno script bash servito ad altre macchine.

## Variabili d'Ambiente

Elenco completo in `.env.example`. Le principali:

| Variabile | Descrizione |
|-----------|-------------|
| `NOTIFYHUB_SECRET_KEY` | Chiave AES-GCM per cifrare `webhook_url` a riposo |
| `DATABASE_URL_OWNER` | Connessione Alembic (`notifyhub_owner`, proprietario dello schema) |
| `DATABASE_URL_APP` / `_AUTH` / `_INGEST` | Le tre connessioni di runtime a RLS (spec 5.2) |
| `DATABASE_URL_SYNC` | Connessione sincrona (psycopg) usata da worker/beat |
| `REDIS_URL` | Broker rate limit, idempotenza, contatori |
| `CELERY_BROKER_URL` | Broker Celery (db Redis separato dal precedente) |
| `NOTIFYHUB_S3_ENDPOINT` / `_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` / `_REGION` | MinIO/S3 |
| `NOTIFYHUB_INLINE_MAX_BYTES` | Soglia inline/object, default 1048576 (1MB, spec 6.5) |
| `NOTIFYHUB_HARD_MAX_BODY_BYTES` | Hard limit di sistema, default 20971520 (20MB) |
| `ALLOW_PUBLIC_REGISTRATION` | Gate su `POST /auth/register`, default `false` |
| `NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST` | Host consentiti per `webhook_url`, CSV |
| `ACCESS_TOKEN_TTL_MINUTES` / `REFRESH_TOKEN_TTL_DAYS` | Scadenze JWT/refresh |
| `CORS_ORIGINS` | Origin ammessi dalla SPA |
| `NOTIFYHUB_PUBLIC_BASE_URL` | URL pubblica dell'istanza: inviti, link delle notifiche, URL di ingestion, script wrapper. Vedi "URL pubblica dietro reverse proxy" |
| `NOTIFYHUB_WRAPPER_SCRIPT_PATH` | Percorso di `notifyhub-run.sh` servito dal pulsante "Scarica lo script". Vuoto = si cerca accanto al codice; serve solo a deploy fuori standard |
| `TRUSTED_PROXIES` | Solo questi IP autorizzano la lettura di `X-Forwarded-For` |
| `SMTP_HOST/_PORT/_USER/_PASSWORD/_FROM` | Opzionali: se assenti, l'invito resta un link copiabile |

## Job di Manutenzione

Nove job Celery Beat, definiti in `app/tasks/maintenance.py` e schedulati in
`app/tasks/celery_app.py` (spec sezione 11). Il worker che li esegue e il servizio `worker`/`beat`
del compose di produzione (profilo di default, non serve attivare nulla).

### 1. `purge_notifications`

**Cosa fa:** per ogni tenant con `retention_days` non NULL, elimina le notifiche piu vecchie della
retention, a batch di 10.000 righe.

**Quando:** ogni notte alle 03:00.

**Importanza:** MEDIA. Se non gira, i tenant con retention configurata accumulano dati oltre il
limite dichiarato.

### 2. `purge_audit_events`

**Cosa fa:** per ogni tenant con `audit_retention_days` non NULL (default 365), elimina gli eventi
di audit piu vecchi della retention, a batch di 10.000 righe.

**Quando:** ogni notte alle 05:00.

**Importanza:** BASSA. Se non gira, la tabella `audit_events` cresce oltre la ritenzione
dichiarata; nessuna funzione si degrada.

**Nota:** la ritenzione dell'audit e separata da quella delle notifiche (`retention_days`, default
90) apposta: l'audit deve poter dire chi ha gestito una notifica anche dopo che la notifica e stata
cancellata. Si imposta da Impostazioni → Generali (solo owner) o con
`PATCH /api/v1/tenant {"audit_retention_days": N}`. NULL = conservazione illimitata.

### 3. `purge_deliveries`

**Cosa fa:** elimina le delivery `sent` piu vecchie di 30 giorni. Le `dead` restano finche non
archiviate manualmente.

**Quando:** ogni notte alle 03:30.

**Importanza:** BASSA. Pulizia della tabella outbox.

### 4. `cleanup_tokens`

**Cosa fa:** elimina refresh token scaduti/revocati e inviti scaduti.

**Quando:** ogni ora.

**Importanza:** BASSA. Housekeeping.

### 5. `reconcile_deliveries`

**Cosa fa:** ripesca le delivery `pending`/`failed` con `next_attempt_at` scaduto (copre un
messaggio Celery perso dal broker) e le `sending` con `locked_at` piu vecchio di 10 minuti (copre
un worker morto a meta lavoro).

**Quando:** ogni 5 minuti.

**Importanza:** CRITICA. E' la garanzia di consegna del pattern outbox (spec 8.2): senza questo job
una delivery persa dal broker resta bloccata per sempre.

**Diagnostica se le delivery restano ferme:**

```bash
docker compose logs beat | grep reconcile-deliveries
docker compose exec worker celery -A app.tasks.celery_app inspect active
```

### 6. `drain_object_deletions`

**Cosa fa:** svuota `pending_object_deletions` cancellando gli oggetti da MinIO. Dopo 10 tentativi
falliti la riga resta e alimenta la metrica `notifyhub_maintenance_job_runs_total{job="drain_object_deletions",outcome="error"}`.

**Quando:** ogni 10 minuti.

**Importanza:** MEDIA. Se non gira, gli oggetti cancellati lato applicativo restano su MinIO.

### 7. `purge_orphan_objects`

**Cosa fa:** elimina gli oggetti del bucket piu vecchi di 24h senza riga corrispondente in
`notifications.storage_key`. Recupera i PUT riusciti con commit Postgres fallito.

**Quando:** ogni notte alle 04:00.

**Importanza:** MEDIA. Previene accumulo di oggetti orfani.

**Attenzione, se si tocca questo job:** l'insieme delle `storage_key` note va
raccolto iterando i tenant con `SET LOCAL app.tenant_id` (`tenant_session_sync`),
mai da una sessione senza contesto di tenant. `notifications` ha
`FORCE ROW LEVEL SECURITY` e il ruolo `notifyhub_app` non ha `BYPASSRLS`: una
lettura senza contesto **non da errore, torna zero righe**, quindi ogni oggetto
oltre le 24h risulterebbe orfano e il job cancellerebbe i payload delle notifiche
ancora in elenco, dichiarandosi riuscito. E' stato un difetto reale: vedi
`docs/REVIEW.md`, "Verifica 3", D1, e il test
`tests/integration/test_review_staging.py`.

**Esecuzione manuale:**

```bash
docker compose run --rm worker celery -A app.tasks.celery_app call app.tasks.maintenance.purge_orphan_objects
```

### 8. `recompute_tenant_usage`

**Cosa fa:** ricalcola lo spazio occupato per tenant (inline + oggetti MinIO), alimenta la gauge
`notifyhub_tenant_storage_bytes` usata dall'enforcement di `max_storage_bytes` (spec 4.1, F7).

**Quando:** ogni notte alle 04:30.

**Importanza:** MEDIA. Se non gira, l'enforcement di `max_storage_bytes` lavora su dati non
aggiornati fino al giorno successivo.

### 9. `check_expected_schedules`

**Ogni 60 secondi.** Sorveglianza dell'attesa dei receiver (dead man's switch):
l'unico job che reagisce a cio' che *non* e' arrivato.

Per ogni tenant attivo, prende i receiver `active` con una politica di attesa
configurata (`missing_severity IS NOT NULL`, indice parziale
`ix_receivers_expected_active`) e confronta `last_notification_at` con la
scadenza calcolata da intervallo o espressione cron piu' tolleranza. Chi ha
sforato produce una notifica sintetica con `severity_source = 'missing'`; chi e'
tornato a inviare dopo un allarme ne produce una `recovered` con severity `info` e
si riarma.

Costo: una query indicizzata per tenant. Un'istanza dove nessuno usa la
sorveglianza non fa nient'altro.

Diagnostica:

```bash
docker compose logs worker | grep expected_schedule
# expected_schedule_missing   receiver_id=... slug=... deadline=...
# expected_schedule_recovered receiver_id=...
# check_expected_schedules_done missing=1 recovered=0
```

Se un receiver allarma ogni giorno senza motivo, i sospetti sono due: il job usa
`--only-on-failure` (i successi non inviano niente, quindi sono assenze), oppure
la tolleranza non copre la durata del job, che invia solo a fine esecuzione.

## Quote per Tenant

L'enforcement delle quote (`app/services/quota.py`) e sincrono, dentro la richiesta di ingestion:
supera `max_notifications_per_day` o `max_storage_bytes` (entrambi NULL = illimitato) e la risposta
e `429` con `type: /problems/quota-exceeded`, nessuna sospensione automatica del tenant. Il campo
`tenants.status` (`active`/`suspended`) e amministrativo: va cambiato esplicitamente via
`PATCH /api/v1/tenant` o direttamente in database, non da un job.

## Audit

Chi ha fatto cosa: `audit_events`, consultabile da **owner e admin** in Impostazioni → Audit e
Impostazioni → Letture e verifiche, o via `GET /api/v1/audit/events`,
`/api/v1/audit/notification-status` e `/api/v1/audit/export` (CSV o JSON, massimo 50.000 righe per
export). Member e viewer ricevono 403.

Cosa aspettarsi:

- **c'e** ogni modifica fatta da una persona autenticata (comprese letture e verifiche delle
  notifiche, singole e in blocco), piu login riusciti, login rifiutati di utenti esistenti e
  logout;
- **non c'e** l'ingestion, ne i job Celery: non hanno un attore umano. Non ci sono nemmeno le
  richieste rifiutate con 403/422, che restano nei log strutturati;
- **non ci sono segreti**: `webhook_url`, hash di password e token, corpi delle notifiche sono
  sostituiti da `[redacted]` nel diff.

La tabella e append-only per l'applicazione (`REVOKE UPDATE`, migrazione 0016): un evento scritto
non si corregge dall'API. Un DBA con accesso diretto al database resta fidato — non c'e firma ne
catena di hash sulle righe.

## Backup e Ripristino

I dati vivono in tre posti:

1. **PostgreSQL**: tabelle, schema, vincoli, policy RLS.
2. **MinIO**: payload di notifiche oltre `NOTIFYHUB_INLINE_MAX_BYTES`.
3. **Redis**: stato transitorio (rate limit, idempotenza, broker Celery) — non serve backup.

### Backup coordinato

```bash
docker compose exec -T postgres pg_dump -U postgres notifyhub > backup.sql

docker compose exec minio mc alias set local http://localhost:9000 "$NOTIFYHUB_S3_ACCESS_KEY" "$NOTIFYHUB_S3_SECRET_KEY"
docker compose exec minio mc mirror local/notifyhub-payloads /tmp/minio-backup
docker compose cp minio:/tmp/minio-backup ./minio-backup
```

### Ripristino

```bash
docker compose exec -T postgres psql -U postgres notifyhub < backup.sql

docker compose cp ./minio-backup minio:/tmp/minio-backup
docker compose exec minio mc mirror /tmp/minio-backup local/notifyhub-payloads
```

## Troubleshooting

### `pending_object_deletions` cresce senza svuotarsi

Il job `drain_object_deletions` non riesce a contattare MinIO, o `attempts` ha superato 10 e la riga
resta ferma di proposito.

```bash
docker compose logs worker beat | grep drain_object_deletions
docker compose exec minio mc ls local/notifyhub-payloads
```

**Fix:** verifica la connettivita verso MinIO (`NOTIFYHUB_S3_ENDPOINT`), poi ri-accoda manualmente
il job con il comando della sezione 5 sopra.

### Rate limiting bloccato

Le chiavi sliding-window sono su Redis:

```bash
docker compose exec redis redis-cli KEYS "ingest:ratelimit:*"
docker compose exec redis redis-cli DEL "ingest:ratelimit:ip:<indirizzo>"
docker compose exec redis redis-cli DEL "ingest:ratelimit:slug:<receiver_id>"
```

Il rate limit per IP (`ingest:ratelimit:ip:*`, 300/min) e il primo gate, valutato prima della
risoluzione dello slug (spec 10.1): uno scan di slug inesistenti resta bloccato li, senza mai
toccare il database.

### RLS blocca query legittime

Se una richiesta autenticata vede righe mancanti o un 404 inatteso, verifica che la transazione
abbia impostato `app.tenant_id`: la dependency FastAPI lo fa con `SET LOCAL`, valido solo fino al
prossimo commit sulla stessa sessione. Un `commit()` intermedio seguito da altre query nella stessa
sessione le esegue senza `app.tenant_id`, e la policy nega di default (nessuna riga, non un errore).

### Webhook non consegnati

```bash
docker compose logs worker
docker compose exec worker celery -A app.tasks.celery_app inspect active
docker compose exec worker celery -A app.tasks.celery_app inspect registered
```

Se `registered` non elenca `app.tasks.delivery.dispatch_delivery`, il worker non ha caricato i
moduli task (verifica `include` in `app/tasks/celery_app.py`). Se il worker e sano ma le delivery
restano `pending`, controlla `GET /api/v1/deliveries?status=pending` e attendi il prossimo giro di
`reconcile_deliveries` (5 minuti) o riavvia il worker:

```bash
docker compose restart worker
```

## Metriche Esposte

L'API espone metriche Prometheus sulla porta interna 9100, mai instradata da nginx (spec 10.4):

```bash
docker compose exec api curl -s http://localhost:9100/metrics
```

Metriche definite in `app/core/metrics.py`:

- `notifyhub_ingestion_requests_total{outcome}` — richieste di ingestion per esito (`success`,
  `replay`, `not_found`, `rate_limited`, `payload_too_large`, `unsupported_media_type`,
  `storage_unavailable`, `error`)
- `notifyhub_ingestion_duration_seconds` — histogram, latenza dell'endpoint di ingestion
- `notifyhub_deliveries_total{outcome}` — tentativi di inoltro per esito
- `notifyhub_maintenance_job_runs_total{job,outcome}` — esecuzioni dei job di manutenzione
- `notifyhub_tenant_storage_bytes{tenant_id}` — spazio occupato per tenant, da `recompute_tenant_usage`

Integrazione Prometheus:

```yaml
scrape_configs:
  - job_name: notifyhub
    static_configs:
      - targets: ['api:9100']
```

## Limitazioni Conosciute

Vedi `notifyhub-spec.md` sezione 16 per i rischi noti e i rimandi consapevoli (ricerca limitata ai
primi 4096 caratteri, nessun partitioning di `notifications`, access token non revocabile prima
della scadenza di 15 minuti).

## Support

Per bug o richieste di funzionalita, la fonte di verita e `notifyhub-spec.md`; lo stato di
implementazione e in `plan_NotifyHub/resume.md`.
