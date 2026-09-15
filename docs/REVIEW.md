# NotifyHub - Revisione di accettazione (fase 10.6)

Data: 2026-08-01
Riferimenti: `notifyhub-spec.md` v0.3, `plan_NotifyHub/overview.md`, `plan_NotifyHub/resume.md`

> **Superata dalla "Verifica 2" in fondo a questo file.** Il repository e stato ricostruito da zero
> dopo questa revisione secondo l'ordine di lavoro raccomandato alla sezione 8: tutti i difetti
> elencati qui sotto (B1-B5, S1-S8, F1-F21) sono stati verificati chiusi o corretti nella Verifica 2,
> incluso un avvio reale dello stack di produzione e l'esecuzione completa di `scripts/smoke.sh`.
> Il contenuto originale resta sotto invariato come registro storico dei difetti trovati.

## Esito

**RESPINTO.** Il piano non e implementato. `plan_NotifyHub/resume.md` dichiara le fasi 0-9 `DONE`
e la fase 10 al 90 per cento; la verifica sul repository mostra che la maggior parte delle
funzionalita dichiarate non esiste, che lo stack non si avvia e che le migrazioni non arrivano a
`head`. Le note di stato in `resume.md` non sono verificabili contro il codice e vanno considerate
non attendibili.

Verifiche eseguite:

- `python3 -m pytest -q` in `backend/`: 125 passed, 8 skipped, 0.60 s
- `find` sull'albero del repository
- lettura di tutti i moduli di `backend/app`, delle migrazioni, dei file di deploy e di `scripts/smoke.sh`

## 1. Funzionalita dichiarate DONE ma assenti dal repository

| Dichiarato in resume.md | Realta |
|---|---|
| Fase 9 - Dashboard React, `T-UI1..19` verdi | La cartella `frontend/` non esiste. Nessun file React, nessun `package.json`, nessun test frontend. `make fe-lint`, `make fe-test`, `make fe-build` falliscono tutti. |
| Fase 6 - Outbound e outbox, `T-OUT1..26` verdi | `app/outbound/` e `app/outbound/formatters/` contengono solo `__init__.py` vuoti. Nessun sender, nessun formatter Slack o Google Chat conforme, nessuna tabella outbox popolata, nessun hook `after_commit`, nessuna macchina a stati. |
| Fase 8 - Manutenzione e osservabilita, `T-MAINT1..23` verdi | `app/tasks/` contiene solo `__init__.py` vuoto. Nessun `celery_app`, nessun task, nessun job Beat. Nessuno dei sette job della spec sezione 11 esiste. `app/core/metrics.py` non esiste, nessun endpoint `/metrics`, nessun `/readyz`. |
| Fase 5 - Ingestion, `T-ING1..24` verdi | L'endpoint `/ingest/{slug}` della spec non esiste (vedi sezione 2). Nessuna normalizzazione UTF-8, nessuna idempotenza `X-Request-Id`, nessun rate limit per IP, nessuna catena di severity. |
| Fase 4 - severity rules con RE2 | `app/services/severity.py` non esiste. `re2` non e importato in nessun punto di `app/`. La catena di severity della spec sezione 7 non e implementata. Nessun endpoint di CRUD delle regole, nessun `test-severity`. L'invariante I-3 e vacuamente vera solo perche nessuna regex utente viene mai valutata. |
| Fase 3 - inviti, registrazione gated | Nessun endpoint `/auth/register`, `/invitations`, `/invitations/accept`. `ALLOW_PUBLIC_REGISTRATION` e letto in configurazione e mai usato. Nessun vincolo ultimo owner. |
| Fase 7 - API di consultazione, paginazione a cursore | `GET /api/v1/notifications` usa `skip`/`limit`. Nessun cursore su `(received_at, id)`, nessun filtro `group_id`, `severity_min`, `q`, `from`, `to`. `GET /notifications/{id}/content` non esiste. `DELETE /notifications/{id}` non esiste. `/stats/summary` non esiste. |
| Fase 1 - suite RLS `T-RLS1..9` verdi | Gli otto test di `tests/integration/` sono `SKIPPED` con motivazione `RLS policies not yet created by migrated_db fixture` e `Alembic upgrade/downgrade requires synchronous engine setup`. L'isolamento fra tenant non e mai stato verificato. |

Endpoint della spec sezione 9 mancanti del tutto: `/api/v1/receivers/*` (dettaglio, patch, delete,
`rotate-slug`, `severity-rules`, `test-severity`, `channels`), `/api/v1/groups/{id}/receivers`,
`/api/v1/groups/{id}/delete-impact`, `/api/v1/tenant`, `/api/v1/channels` (esiste
`/api/v1/delivery/channels`, path diverso), `/api/v1/channels/{id}/test`, `/api/v1/deliveries`,
`/api/v1/deliveries/{id}/retry`, `/api/v1/notifications/bulk-read`, `/api/v1/stats/summary`.

## 2. Difetti bloccanti

### B1 - L'endpoint di ingestion della spec non esiste

Spec sezione 6.2 e 9.1: `POST /ingest/{slug}`, pubblico, corpo `text/plain`, lo slug e l'unica
credenziale, risposta `201 {"id", "severity", "forwarded_to"}`.

Implementato in `backend/app/api/v1/ingestion.py`: `POST /api/v1/ingestion` e
`POST /api/v1/ingestion/{receiver_slug}`, corpo JSON `{title, body, severity, metadata}`, protetti
da una API key Bearer, risposta `202 {"notification_id"}`. Le API key sono un'entita inventata
(`app/models/api_key.py`, migrazione `0005`) che non compare ne nella spec ne nel piano e che
contraddice il modello di sicurezza scelto.

Conseguenza: nessuno degli esempi `curl`/`wget` della spec funziona, e lo scenario di accettazione
della sezione 12 non e riproducibile.

### B2 - Il percorso di ingestion non puo funzionare comunque

`app/services/ingestion.py:72` costruisce `Notification(title=..., body=...)`. Il modello
`app/models/notification.py` non ha ne `title` ne `body`: ha `content`, `content_preview`,
`content_size`, `content_normalized`, `severity_source`, `received_at`. La chiamata solleva
`TypeError` al primo invio reale. Anche superandola, `content_preview`, `content_size`,
`severity_source` e `received_at` sono `NOT NULL` e non vengono mai valorizzati.

Nessun test copre il percorso: `tests/unit/test_ingestion.py` valida solo lo schema Pydantic.

### B3 - `alembic upgrade head` fallisce

`0001_schema_iniziale.py` crea gia `delivery_channels`, `groups`, `group_channel_bindings`,
`receiver_channel_overrides`, `pending_object_deletions`. Le migrazioni successive le ricreano:

- `0007_delivery_channels.py` -> `create_table("delivery_channels")`
- `0008_groups_and_bindings.py` -> `groups`, `group_channel_bindings`, `receiver_channel_overrides`
- `0011_pending_object_deletions.py` -> `pending_object_deletions`

La catena si ferma su `DuplicateTable` alla revisione `0007`. Il servizio `migrate` del compose non
completa, quindi `api`, `worker` e `beat` (che dipendono da `service_completed_successfully`) non
partono mai. Il database di produzione non e creabile.

### B4 - I container non si avviano

- `deploy/api/Dockerfile` esegue `COPY backend/ .`: nell'immagine esiste `/app/app`, non esiste
  `/app/deploy`. Il comando `bash deploy/api/entrypoint.sh` del servizio `api` fallisce subito.
- `entrypoint.sh` avvia `app.main:metrics_app`, oggetto che non esiste in `app/main.py`.
- L'healthcheck di `api` chiama `curl -f http://localhost:8000/readyz`: `curl` non e installato
  nell'immagine `python:3.12-slim` e `/readyz` non e implementato. L'healthcheck non puo diventare
  verde, quindi `nginx` (che dipende da `api: service_healthy`) non parte mai.
- `worker` e `beat` lanciano `celery -A app.tasks.celery_app`: il modulo non esiste, crash-loop.
- Il servizio `nginx` costruisce `deploy/frontend/Dockerfile`, che fa `COPY frontend/ .` e
  `npm run build`: senza la cartella `frontend/` la build fallisce e con essa l'intero
  `docker compose up`.
- `.env.example` punta tutte le URL a `localhost`. Dentro un container `localhost` e il container
  stesso: nessun servizio raggiunge Postgres, Redis o MinIO.

### B5 - `scripts/smoke.sh` non e mai stato eseguito

- Riga 297: `404_nonexistent="$body"`. In bash un nome di variabile non puo iniziare con una cifra:
  errore di sintassi allo startup dello script, prima di qualunque assert.
- Chiama endpoint inesistenti: `/ingest/{slug}`, `/api/v1/groups/{id}/receivers`,
  `/api/v1/receivers/{id}`, `/api/v1/receivers/{id}/severity-rules`,
  `POST /api/v1/groups/{g}/channels/{c}`, `/api/v1/notifications/{id}/content`.
- Il bootstrap del passo 2 importa `app.core.config.config` e `app.db.session.get_session`, due
  simboli che non esistono.

`resume.md` lo dichiara "acceptance test with 17 assertions". Nessuna assertion e mai stata valutata.

## 3. Difetti di sicurezza

### S1 - L'invariante I-2 (404 uniforme) e violata

`ingest_by_slug` risponde `404` per slug inesistente o receiver disabilitato, ma `401` quando lo
slug e valido e la API key manca o e sbagliata. Chi possiede una lista di slug distingue quelli
validi dal codice di risposta: e esattamente l'oracolo di enumerazione che la spec sezione 9.1
esclude. Il tenant `suspended` non e verificato affatto in ingestion.

### S2 - Tabelle senza RLS e senza GRANT

`0003_rls.py` esegue `GRANT ... ON ALL TABLES` e abilita RLS al momento della revisione `0003`.
Le tabelle create dopo non sono coperte:

- `api_keys` (0005) e `delivery_attempts` (0006): nessuna RLS, nessuna policy. Con un solo
  `notifyhub_app` condiviso fra tenant, **qualunque tenant puo leggere e modificare le API key e i
  tentativi di consegna di tutti gli altri**. Viola I-1.
- `delivery_channels`, `groups`, `group_channel_bindings`, `receiver_channel_overrides` ricreate da
  0007 e 0008: perdono RLS e GRANT assegnati a 0003 (nella misura in cui la catena arrivasse a
  eseguirle).
- `pending_object_deletions` ricreata da 0011: perde le GRANT.

`ALTER DEFAULT PRIVILEGES` non e mai impostato, quindi il problema si ripresentera a ogni nuova
tabella.

### S3 - Refresh token con scadenza immediata

`app/api/v1/auth.py:102` e `:183`: `expires_at=datetime.utcnow()`. Il token nasce gia scaduto.
`refresh_token_ttl_days` e in configurazione e non viene mai usato. Nessun punto del codice
controlla `expires_at` in fase di refresh: la scadenza non e ne impostata ne verificata.

### S4 - Famiglia di refresh token coincidente con l'utente

`family_id_val = user_identity.id`: tutte le sessioni di un utente condividono la stessa famiglia.
Il riuso di un singolo token revoca tutte le sessioni dell'utente su tutti i dispositivi. La spec
sezione 4.1 prevede una famiglia per catena di rotazione.

### S5 - Rate limit del login come vettore di lockout

`rate_limit_key = f"login_attempts:{body.email}"`, 5 tentativi ogni 900 secondi. La spec sezione
10.2 chiede 10 tentativi per `(email, IP)`. Chiave sulla sola email significa che chiunque conosca
un indirizzo puo bloccare quell'account inviando 5 richieste. Il contatore viene incrementato anche
sui login riusciti.

### S6 - Il rate limiter conta le richieste rifiutate

`app/services/ratelimit.py`: `zadd` avviene nella stessa pipeline della lettura, prima della
decisione. Una richiesta bloccata entra comunque nella finestra e sposta in avanti la scadenza del
blocco: sotto pressione il limite non si riapre piu. Inoltre il membro del sorted set e
`str(now)` in millisecondi, quindi due richieste nello stesso millisecondo collidono e vengono
contate come una sola.

Manca del tutto il contatore per IP (300/min) che la spec sezione 10.1 vuole **come primo gate**,
prima della risoluzione dello slug.

### S7 - `webhook_url` non cifrato

`app/api/v1/delivery.py:41` assegna `webhook_url=body.webhook_url` direttamente. La spec sezione
4.3 e 10.3 richiedono AES-GCM con chiave da `NOTIFYHUB_SECRET_KEY`. `app/core/crypto.py` espone
solo hashing di password. Il webhook e inoltre restituito in chiaro da `DeliveryChannelOut` a meno
che lo schema non lo mascheri: da verificare, ma la cifratura a riposo manca in ogni caso. Viola I-6.

### S8 - `X-Forwarded-For` e `trusted_proxies`

`source_ip` non viene mai valorizzato e `trusted_proxies` non e mai usato. Il campo audit della
spec sezione 4.2 resta sempre nullo.

## 4. Difetti funzionali e di correttezza

| # | File | Problema |
|---|---|---|
| F1 | `app/services/storage.py:15` | La soglia di offload e `hard_max_body_bytes // 2`, cioe 10 MB. La spec sezione 6.5 impone `INLINE_MAX_BYTES` = 1 MB. `notifyhub_inline_max_bytes` e configurato e mai letto. Un payload da 2 MB resta inline. |
| F2 | `app/services/storage.py:22` | Chiave oggetto `notifications/{id}/body.txt`. La spec vuole `{tenant_id}/{yyyy}/{mm}/{dd}/{id}.txt`: senza prefisso per tenant il purge per tenant e la lifecycle policy non sono implementabili. |
| F3 | `app/services/storage.py` | Usa `boto3` sincrono dentro funzioni `async`: ogni PUT o GET blocca l'event loop dell'API per tutta la durata del trasferimento. La spec sezione 13 prescrive `aioboto3` sull'API. Il client viene inoltre ricreato a ogni chiamata. |
| F4 | `app/services/ingestion.py:70` | Con `storage_backend = "object"` scrive `content = ""`, non `NULL`. Il vincolo `ck_notifications_body` richiede `content IS NULL`: violazione del CHECK al primo payload offloaded. |
| F5 | `app/api/v1/ingestion.py:20` | Il controllo dei 20 MB avviene su un corpo gia interamente deserializzato da Pydantic. La spec sezione 6.5 vuole lettura in streaming con interruzione al superamento della soglia. `proxy_request_buffering off` in nginx non serve a nulla se l'applicazione bufferizza comunque. |
| F6 | ingestion | Nessuna normalizzazione UTF-8 e nessuna rimozione dei byte NUL. Un corpo con `\x00` fa fallire l'INSERT su Postgres. Viola I-7. |
| F7 | `app/api/v1/ingestion.py:64` | La risoluzione dello slug usa `auth_session()`, cioe il ruolo `notifyhub_auth`, che ha `SELECT` solo su `users`, `refresh_tokens`, `invitations`. La lettura di `receivers` viene negata: il percorso e comunque morto. Il pool `notifyhub_ingest` esiste in `db/session.py` e non e usato da nessuno. Viola I-1. |
| F8 | `app/db/session.py:50` | `SET LOCAL` vale fino al commit. `tenant_session` fa `commit()` in uscita e i chiamanti (per esempio `ingest_notification`) chiamano `commit()` a loro volta: qualunque statement emesso dopo il primo commit gira senza `app.tenant_id` e cade nel deny di RLS, in modo silenzioso e dipendente dall'ordine. |
| F9 | `app/db/session.py:11` | Gli engine leggono `os.environ` con un fallback `postgresql+asyncpg://user:pass@localhost/db`. Una variabile mancante non produce un errore di avvio ma un errore di connessione a runtime. `Settings` non viene usato. |
| F10 | `app/api/v1/notifications.py:46` | Il conteggio totale carica tutte le righe in memoria (`len(result.scalars().all())`) e lo ripete per il conteggio dei non letti: tre query complete per pagina. Su un tenant con milioni di notifiche l'endpoint e inutilizzabile. |
| F11 | `app/api/v1/auth.py:238` | `select(User).where(User.id == claims.sub)` confronta una colonna UUID con una stringa; idem `Tenant.id == claims.tid`. Su asyncpg questo solleva errore invece di filtrare. |
| F12 | `app/cli.py:45` | Il bootstrap esegue `Base.metadata.create_all`, scavalcando Alembic: crea uno schema senza RLS, senza trigger e senza vincoli. Va usato `alembic upgrade head`. Inoltre le opzioni sono `--tenant-name/--owner-email/--owner-password`, mentre la spec sezione 10.2 documenta `--tenant-name/--email`, e il modulo e `app.cli`, non `notifyhub.cli`. |
| F13 | `app/main.py` | Nessun middleware CORS, benche `cors_origins` sia configurato. Una SPA su un'altra origine non potrebbe chiamare l'API. |
| F14 | `app/main.py:35` | L'handler di `HTTPException` assegna a ogni errore il tipo `PROBLEM_TYPES["not_found"]`: un 401 o un 500 vengono etichettati come "not found". |
| F15 | `app/api/deps.py:13` | `authorization: str = Header(...)` rende l'header obbligatorio a livello di validazione: una richiesta senza header riceve `422`, non `401`. |
| F16 | `app/services/delivery.py:13` | Ridefinisce un enum `ChannelType` locale con i valori `email` e `webhook`, in conflitto con `app/db/types.py:ChannelType`. Nessuna cifratura, nessun rispetto di `Retry-After`, nessuna distinzione fra 4xx e 5xx: `send_to_webhook` restituisce solo `True`/`False`. La macchina a stati della spec sezione 8.2 non esiste. |
| F17 | `app/services/storage.py:68` | Il backoff e 2, 4, 8, 16, 32 secondi. La spec sezione 8.2 prescrive 30 s, 2 m, 10 m, 1 h, 6 h con jitter. Nessun jitter. |
| F18 | `app/services/delivery.py:61` | Il formatter Slack inserisce `payload.body` senza troncamento: oltre 3000 caratteri Slack rifiuta il blocco. Nessun link alla notifica in dashboard, nessuna indicazione di troncamento. Il formatter Google Chat usa `cards` v1, la spec chiede `cardV2`. |
| F19 | vari | `datetime.utcnow()` usato in `cli.py`, `auth.py`, `services/ingestion.py`, `core/security.py`: deprecato e naive, mentre le colonne sono `timestamptz`. |
| F20 | `app/models/notification.py:43` | L'indice full-text e dichiarato `gin_trgm_ops` su una colonna testuale, mentre la spec sezione 4.2 prescrive `gin (to_tsvector('simple', content_preview))`. `gin_trgm_ops` richiede l'estensione `pg_trgm`, che nessuna migrazione crea. |
| F21 | `deploy/postgres/initdb/00-roles.sql` | Password di sviluppo in chiaro, identiche in produzione perche `.env.example` le riusa. Nessun percorso documentato per cambiarle prima del primo avvio. |

## 5. Deviazioni dal piano

Il piano vieta esplicitamente di inventare file, dipendenze e funzionalita non nominate. Sono state
aggiunte, con relative migrazioni e test:

- API key per receiver (`models/api_key.py`, migrazione 0005)
- template di notifica (`models/template.py`, `services/template.py`, `schemas/template.py`)
- operazioni batch (`api/v1/batch.py`, `schemas/batch.py`)
- ricerca avanzata (`api/v1/search.py`, `schemas/search.py`)
- rate limiting a tier con token bucket (`services/advanced_ratelimit.py`, enum `RateLimitTier`)
- `delivery_attempts` (migrazione 0006)
- `notifications.archived_at` (migrazione 0009)

Nessuna di queste compare nella spec o nel piano. I commit `32381af` e `23ce7c3` sono etichettati
"Phase 10" e "Phase 11" di una numerazione che non esiste nel piano. Il tempo speso qui e stato
sottratto a outbound, manutenzione e frontend, che sono rimasti vuoti.

## 6. Qualita dei test

125 test in 0,60 secondi, nessun accesso reale al database nella pratica. Problemi strutturali:

- `tests/conftest.py:41` usa `Base.metadata.create_all` invece delle migrazioni: lo schema di test
  non ha RLS, ne trigger `updated_at`, ne trigger di cancellazione oggetti, ne il CHECK
  `ck_notifications_body`. La decisione D5 del piano (servizi reali, nessun mock del database) e
  formalmente rispettata e sostanzialmente aggirata.
- Le DDL di test girano sull'engine `notifyhub_app`, che non e proprietario dello schema.
- `tests/conftest.py:155` la fixture `auth_token` restituisce `None` se il login fallisce, invece di
  fallire. Ogni test che la usa passa anche quando l'autenticazione e rotta.
- Gli otto test di integrazione sono tutti skippati, compresa l'intera suite RLS.
- Le cinque "verifiche di autenticita" richieste dal piano (rompere il codice e vedere il test
  diventare rosso) risultano tutte `TODO` in `resume.md`, coerentemente con il fatto che i test che
  dovrebbero diventare rossi non esistono.

## 7. Cosa e effettivamente utilizzabile

Non tutto e da buttare. Sono in buono stato e riusabili:

- `alembic/versions/0001_schema_iniziale.py` e `0002_indici_vincoli_trigger.py`: schema, indici,
  trigger `updated_at` e trigger di accodamento delle `storage_key` sono aderenti alla spec.
- `alembic/versions/0003_rls.py`: policy corrette, con `current_setting('app.tenant_id', true)` e
  `FORCE ROW LEVEL SECURITY`; va solo estesa alle tabelle mancanti e resa idempotente rispetto alle
  migrazioni successive.
- `app/models/*`: i modelli riflettono lo schema della spec, `metadata` e mappato correttamente su
  `meta`.
- `app/core/errors.py`, `app/core/logging.py`: formato RFC 7807 unico e log strutturati con
  `request_id`.
- `deploy/nginx/nginx.conf`: `client_max_body_size 20m` e `proxy_request_buffering off` su
  `/ingest/` sono corretti.
- `deploy/postgres/initdb/00-roles.sql`: i quattro ruoli sono creati senza `BYPASSRLS`, come da D3.

## 8. Ordine di lavoro consigliato

1. Riportare `resume.md` allo stato reale. Nessun'altra attivita ha senso finche il tracciamento
   mente.
2. Rimuovere o mettere da parte le funzionalita fuori piano (API key, template, batch, search,
   advanced ratelimit) e le migrazioni 0005-0011 duplicate. Ricostruire una catena Alembic che
   arrivi a `head`.
3. Chiudere B3 e B4: migrazioni verdi e stack che si avvia. Senza questo nulla e verificabile.
4. Rifare la fase 5 secondo la spec: `POST /ingest/{slug}` pubblico, testo semplice,
   normalizzazione, streaming con limite, 404 uniforme, idempotenza, catena di severity con
   `app/services/severity.py` e `re2`.
5. Sostituire `conftest.py` con una fixture che applica le migrazioni, poi sbloccare la suite RLS e
   pretendere che sia verde.
6. Fase 6 e fase 8 da zero: outbox, worker Celery, formatter, job di manutenzione, metriche,
   `/readyz`.
7. Fase 9 da zero.
8. Riscrivere `scripts/smoke.sh` contro gli endpoint reali e farlo girare in CI.

---

## Verifica 2 — 2026-08-01

Riferimenti: gli stessi di sopra, piu `docker-compose.yml`, `deploy/api/Dockerfile`,
`scripts/smoke.sh`, `app/tasks/celery_app.py`, `app/api/ingest.py`.

### Esito

**ACCETTATO.** Fra la revisione originale e questa, il repository e stato ricostruito seguendo
l'ordine di lavoro raccomandato alla sezione 8: rimosse le funzionalita fuori piano e le migrazioni
duplicate, ricostruita la catena Alembic (0001-0005, lineare), riscritte ingestion, outbound, worker
Celery, manutenzione e frontend secondo la spec. Questa verifica ha controllato quel lavoro contro
il codice reale — non contro le dichiarazioni di stato — eseguendo la suite completa, il compose di
sviluppo e per la prima volta il compose di produzione con `scripts/smoke.sh` fino in fondo.

Verifiche eseguite:

- `python3 -m pytest -q` in `backend/` (servizi reali via `docker-compose.test.yml`, nessun mock):
  **148 passed, 0 skipped**, ~3.9s. `ruff format --check`, `ruff check`, `mypy` puliti.
- `npm run lint`, `npm run test -- --run` (23 test, 14 file), `npm run build` in `frontend/`: puliti.
- `docker compose build` (tutte le immagini, incluso `nginx` con la build di `frontend/`) e
  `docker compose up -d` sul compose di produzione: `postgres`, `redis`, `minio`, `migrate` (exit 0,
  migrazioni a `head`), `api`, `worker`, `beat`, `nginx` tutti sani.
- `scripts/smoke.sh` eseguito per intero contro lo stack containerizzato reale (nginx davanti, non
  `httpx.ASGITransport`): **22/22 assert, SMOKE OK, exit 0**. Copre lo scenario della spec sezione 12
  end-to-end, incluso l'invariante I-2 (404 uniforme), l'idempotenza su `X-Request-Id`, l'offload
  MinIO con download byte-identico, e la consegna reale del worker Celery al webhook mock.

### Difetti trovati e corretti in questa verifica

Il codice applicativo era in gran parte corretto (confermato dai 145 test preesistenti), ma i file
di deploy e lo smoke test erano rimasti scritti per uno stato del repository precedente
all'aggiunta di `app/outbound/`, `app/tasks/` e `frontend/`, e non erano mai stati eseguiti contro
il codice reale. Nessuno di questi difetti era coperto da un test che lo avrebbe fatto emergere
prima di un avvio reale dello stack:

| # | File | Difetto | Correzione |
|---|---|---|---|
| D1 | `docker-compose.yml` | `worker`/`beat` dietro il profilo `workers`, con un commento che li dichiarava non attivabili perche `app.tasks.celery_app` "oggi assente" | Il modulo esiste da tempo: spostati nel profilo di default |
| D2 | `docker-compose.yml` | `nginx` usava l'immagine stock con la sola configurazione montata ("la SPA non esiste ancora") | `frontend/` esiste e builda: passato a `build: deploy/frontend/Dockerfile` |
| D3 | `deploy/api/Dockerfile` | Non copiava `deploy/api/entrypoint.sh` (il Dockerfile copia solo `backend/`); il servizio `api` falliva subito con "No such file or directory" | Aggiunta `COPY deploy/api/entrypoint.sh deploy/api/entrypoint.sh` |
| D4 | `app/tasks/celery_app.py` | Nessun `include=[...]`: il worker reale (`celery -A app.tasks.celery_app`) partiva con `[tasks]` vuoto, zero task registrati nonostante fossero correttamente decorati con `@celery_app.task` in `app/tasks/delivery.py` e `app/tasks/maintenance.py` | Aggiunto `include=["app.tasks.delivery", "app.tasks.maintenance"]`. Nuovo test `tests/unit/test_celery_app.py`, verificato che fallisce senza la correzione |
| D5 | `app/api/ingest.py` | `_validate_content_type` rifiutava con 415 qualunque Content-Type diverso da `text/plain`, incluso `application/x-www-form-urlencoded` che curl `--data` e wget `--post-data` (i due client della spec 6.2) impostano da soli quando non specificato: nessuno degli esempi curl della spec avrebbe funzionato davvero | Esteso l'insieme accettato. Nuovo test `test_content_type_form_urlencoded_di_curl_e_wget_e_accettato` |
| D6 | `scripts/smoke.sh:297` | `404_nonexistent="$body"`: nome di variabile bash che inizia per cifra, gia segnalato come B5 nella revisione originale e mai corretto | Rinominata `body_404_nonexistent` |
| D7 | `scripts/smoke.sh` | Ogni `((var++))` con `var` a zero: sotto `set -e`, l'espressione aritmetica che vale 0 restituisce uno stato di uscita non-zero e termina lo script silenziosamente alla primissima occorrenza (il ciclo di attesa di `/readyz`) | Sostituiti tutti con `var=$((var+1))` |
| D8 | `scripts/smoke.sh` | Il bootstrap del tenant importava `app.core.config.config` e `app.db.session.get_session`, due simboli inesistenti | Sostituito con l'invocazione reale, `python -m app.cli bootstrap --tenant-name ... --email ... --password ...` |
| D9 | `scripts/smoke.sh` | Email `owner@test.local`: `.local` e un nome a uso speciale (RFC 2606) rifiutato da `EmailStr` | Cambiata in un dominio sintatticamente normale |
| D10 | `scripts/smoke.sh` | Payload di creazione canale privo del campo obbligatorio `name`; payload di creazione severity-rule privo del campo obbligatorio `priority`; URL di bind gruppo-canale con `channel_id` nel path invece che nel body; path del canale `/api/v1/delivery/channels` invece di `/api/v1/channels` | Corretti tutti e quattro contro lo schema/router reali |
| D11 | `scripts/smoke.sh` | L'allowlist webhook (`NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST=mock-webhook`) veniva esportata nell'ambiente del processo bash, mai letta dal container `api` | Aggiunta interpolazione `${NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST:-...}` nell'`environment` del servizio `api` in `docker-compose.yml`, piu l'export spostato prima di `docker compose up` |
| D12 | `scripts/smoke.sh` | Il test del payload da 2MB non alzava mai il cap `max_body_bytes` (il receiver eredita il cap del tenant, 1MB di default, alla creazione): avrebbe sempre dato 413 | Aggiunte due `PATCH` (tenant e receiver) prima dell'invio |
| D13 | `scripts/smoke.sh` | Il test dell'oversize inviava un messaggio di esattamente 100 byte contro un limite di 100 byte: il confronto e `> max_bytes`, non `>=`, quindi il limite non veniva mai superato | Messaggio allungato oltre 100 byte |

### Esito per invariante

Tutti gli invarianti I-1..I-9 di `plan_NotifyHub/overview.md` sono stati osservati veri durante
l'esecuzione dello smoke test reale (non solo dedotti dal codice): in particolare I-2 (404 uniforme)
e I-5 (enqueue solo dopo il commit, dimostrato dalla consegna effettiva al webhook mock) sono stati
verificati end-to-end contro lo stack containerizzato, non contro `httpx.ASGITransport`.

### Stato per fase

Vedi `plan_NotifyHub/resume.md`: tutte le fasi 0-10 sono `DONE`. Nessun blocco aperto.

---

## Verifica 3 — 2026-08-04 (funzioni aggiunte in sessione)

Rilettura di quanto costruito dopo la Verifica 2: soglia di durata (migrazione
`0010`), slug parlante e URL pubblica (`0011`), sorveglianza dell'attesa (`0012`),
fase dell'esecuzione (`0013`), allineamento della validazione delle email.

Metodo: per ogni ipotesi di difetto, un esperimento prima della correzione. Solo
quelle confermate sono elencate qui, ognuna con il test che le tiene chiuse.

### Difetti trovati e corretti

| # | Dove | Difetto | Effetto reale | Correzione e test |
|---|---|---|---|---|
| R1 | `app/services/surveillance.py`, `api/v1/receivers.py` | Un'espressione cron o un fuso non calcolabili letti da colonna facevano uscire l'eccezione di `croniter`/`zoneinfo` da `alert_deadline` | `GET /api/v1/receivers` rispondeva **500**: un solo receiver malformato rendeva inutilizzabile ogni elenco della dashboard, selettori dei canali compresi | Errori incapsulati in `InvalidScheduleError`, chiamante che lascia la scadenza vuota e registra `expected_schedule_invalid`. `tests/e2e/test_review_regressioni.py` (3 test) |
| R2 | `app/tasks/maintenance.py` | Stessa eccezione dentro il ciclo del job | Il job `check_expected_schedules` **moriva a ogni giro**: sorveglianza spenta per *tutti* i tenant, in silenzio, per colpa di una riga | Try/except per receiver, il rotto viene saltato e registrato. Test: il receiver sano riceve l'assenza, il rotto no |
| R3 | `api/v1/receivers.py` (replay) | Il replay rivalutava anche le notifiche scritte dal server (`missing`, `recovered`) e i ping di avvio | Su un receiver sorvegliato di una macchina spenta erano la maggioranza delle ultime notifiche: la risposta "cosa cambierebbe" non mostrava piu' i messaggi veri | Filtro `severity_source NOT IN (missing, recovered)` + `phase IS DISTINCT FROM 'start'`. Due test: le sintetiche escluse, le `phase` NULL conservate |
| R4 | `api/v1/receivers.py` (replay) | Prima stesura del filtro con `IS NOT 'start'` | `sqlalchemy`/Postgres rifiutavano la query: replay rotto per tutti | `is_distinct_from`, che tratta NULL come valore distinto. Colto dai test e2e esistenti sul replay |
| R5 | `scripts/notifyhub-run.sh` | `NOTIFYHUB_PING_START=true` non riconosciuto (solo `1`) | Chi esportava una variabile booleana non aveva ping di avvio, **senza nessun errore** | Accettati `1|true|yes|on`. `tests/unit/test_wrapper_behaviour.py`, parametrizzato |
| R6 | `scripts/notifyhub-run.sh` | `--ping-start` insieme a `--only-on-failure` non avvisava | Avvii sempre inviati, conclusioni solo sui fallimenti: il server vedeva **ogni esecuzione riuscita come interrotta a meta'** | Avviso su stderr (non un errore: non si spegne il cron di nessuno) con l'alternativa `--severity-ok debug` |
| R7 | `app/schemas/receiver.py` | Cron e fuso validati sulla forma ripulita ma salvati grezzi | `"  0   3 * * 1-5 "` restava in colonna e la dashboard lo mostrava con la spaziatura sbagliata | `AfterValidator` di normalizzazione su entrambi i campi, in creazione e in PATCH |

### Verificato e trovato corretto

- **Gemello sincrono dell'instradamento** (`create_deliveries_for_notification_sync`,
  il pezzo piu' a rischio: due percorsi per la stessa regola). Mute per receiver,
  override della soglia e canale disabilitato valgono per l'allarme di assenza
  esattamente come per un messaggio inviato, e l'allarme arriva davvero al webhook.
  `tests/integration/test_surveillance_outbound.py` (5 test, consegna reale con
  `respx`).
- **Battito e idempotenza**: un reinvio con lo stesso `X-Request-Id` risponde 200
  senza scrivere e **non** sposta l'ultima conclusione, quindi un cron che ritenta
  non tiene viva la sorveglianza di un job morto.
- **Ping di avvio**: aggiorna `last_start_at` e non `last_notification_at`, quindi
  non maschera un job che muore a meta'.
- **Durate**: la stessa esecuzione si legge uguale nel log di cron, su Slack e in
  dashboard (`frontend/src/lib/__tests__/duration.test.ts` replica le tabelle dei
  test Python).
- **Wrapper**: exit code del comando restituito al chiamante, severity non valida
  rifiutata prima di eseguire, slug mancante rifiutato, slash finale dell'URL non
  raddoppiato (21 test che eseguono lo script per davvero, in `--dry-run`).

### Scelte consapevoli fissate da un test

- **La quota giornaliera del tenant non sopprime gli allarmi della sorveglianza.**
  L'ingestion oltre quota riceve `429`, ma la notifica "il job non gira piu'"
  viene scritta comunque: un allarme silenziato da una quota sarebbe silenzio
  proprio nel momento in cui serve parlare.
- **Un receiver gia' in ritardo allarma subito** quando si accende la
  sorveglianza, mentre un receiver che non ha mai ricevuto niente ha una finestra
  intera di tolleranza (`expected_since`). L'asimmetria e' voluta: del primo si
  conosce il ritmo, del secondo no.
- **Lo slug resta leggibile a chiunque veda il receiver, `viewer` compreso** (era
  cosi' anche prima di questa sessione, e lo script scaricabile non aggiunge
  esposizione). Chi ha accesso in lettura a un gruppo puo' quindi inviare a quel
  receiver: se un giorno servisse distinguere, la sede e' la matrice dei ruoli
  della spec §4.1, non l'endpoint di download.

### Copertura dopo la verifica

`backend/`: 541 test (0 skippati), `ruff format`/`ruff check`/`mypy` puliti.
`frontend/`: 96 test, `tsc --noEmit` ed eslint puliti.

---

## Verifica 4 — 2026-08-04 (copertura dei test, prima della produzione)

Obiettivo: bloccare le regressioni delle evolutive future. Prima misura, poi
tappa i buchi in ordine di rischio.

### La misura era sbagliata

`pytest --cov` riportava **76%**, e la prima cosa da correggere e' stata la misura:
SQLAlchemy async esegue il lavoro del driver dentro un greenlet
(`greenlet_spawn`), e senza `concurrency = ["greenlet", "thread"]` coverage.py non
traccia quelle righe. Misurato sullo stesso sottoinsieme di test:
`app/api/v1/auth.py` passava da **32% a 54%** solo cambiando la configurazione.

Un numero sbagliato e' peggio di nessun numero: manda a scrivere test dove non
servono e nasconde i buchi veri. La configurazione ora sta in
`backend/pyproject.toml` (`[tool.coverage.run]`, branch coverage attiva).

| | prima (misura corretta) | dopo |
|---|---|---|
| backend, righe + rami | 86% | **90,4%** |
| backend, test | 541 | **600** |
| frontend, righe | 84,8% | **87,1%** |
| frontend, rami | 76,2% | **78,5%** |
| frontend, test | 96 | **115** |

### Difetti trovati scrivendo i test

| # | Dove | Difetto | Effetto |
|---|---|---|---|
| C1 | `app/cli.py` | `bootstrap` con un'email gia' registrata creava il tenant, poi falliva sull'owner e **lasciava un tenant senza nessun utente** | Installazione fantasma: nessuno puo' entrarci, non compare da nessuna parte, ma tutti i job di manutenzione la iterano per sempre. Corretto con controllo preventivo dell'email + compensazione (cancella il tenant) se l'inserimento dell'owner fallisce comunque |
| C2 | `app/core/errors.py` | Le risposte d'errore uscivano con `application/json` invece di `application/problem+json` | Deviazione dalla spec §9 (RFC 7807), mai notata perche' **nessun test guardava il content-type**. Un client che distingue gli errori dal media type non funzionava |
| C3 | `frontend/src/pages/LoginPage.tsx` | `error?.extra.retry_after`: l'optional chain copriva `error`, non `extra` | **Schermata bianca sulla pagina di accesso** a ogni errore senza `extra`, cioe' a ogni guasto di rete: server irraggiungibile, TLS, offline. Nel momento peggiore, perche' l'utente non riesce nemmeno a entrare per capire. Corretto in due punti: `?.` sulla lettura e, soprattutto, `api/client.ts` che ora converte i guasti di `fetch` in un `ApiError` completo, per tutte le pagine |

### Test placebo rimossi

`tests/e2e/test_errors.py` conteneva due test che chiamavano `GET /healthz` e
asseriva 200, con un commento che diceva "per ora verifichiamo che healthz
funzioni". Erano verdi e non verificavano niente di cio' che il nome promette: e'
cosi' che C2 e' rimasto nascosto. Sostituiti con 9 test sulla forma vera delle
risposte d'errore (422, 401, 404, 405, 413, 415, corpo RFC 7807 completo, nessun
dettaglio interno esposto).

### Buchi chiusi, in ordine di rischio

| Area | Prima | Perche' rischiava | Ora |
|---|---|---|---|
| `app/core/readiness.py` — `/readyz` | **0%** | Ci si appoggiano l'healthcheck del Compose e l'HEALTHCHECK dell'immagine all-in-one: se risponde sempre 200 nasconde un guasto, se risponde sempre 503 blocca un deploy | 8 test: verde con le dipendenze reali, 503 con una sola giu', i tre controlli che tornano False invece di propagare l'eccezione |
| `POST /invitations/accept` | non coperto | E' la strada con cui entra **ogni utente dopo il primo** | 10 test: giro completo invito→accettazione→login, token usa e getta, scaduto, revocato, email gia' registrata (409, non 500), tenant sospeso, matrice dei ruoli |
| Canali, binding, override | 61% | Decidono **dove finiscono le notifiche**: un errore qui non da' errore, smette solo di arrivare qualcosa | 13 test: cicli di vita completi, webhook mai in chiaro in nessuna lettura, host fuori allowlist (SSRF), idempotenza dell'override, isolamento fra tenant |
| `app/api/v1/tenant.py` + quote | 48% / 71% | I numeri che spengono l'ingestion con 429 | 13 test, ramo di `max_storage_bytes` compreso |
| `app/cli.py` | 46% | Se il bootstrap si rompe, l'installazione e' morta | 4 test che eseguono `python -m app` come **sottoprocesso**, cioe' come gira in produzione (in-process non si puo': `asyncio.run` dentro un event loop) |
| `scripts/notifyhub-run.sh` | nessun test di comportamento | Gira in cron su macchine altrui | 21 test che eseguono lo script in `--dry-run` |
| `ChannelBindings.tsx` (frontend) | **2,35%** | E' la tabella che decide **chi viene svegliato di notte** | 5 test: POST/PUT/DELETE secondo la transizione, errore visibile |
| `LoginPage.tsx` | 74% righe, **14% rami** | Se si rompe, nessuno entra | 6 test: credenziali sbagliate, rate limit coi minuti, doppio invio, guasto di rete |
| `NotificationDetailPage.tsx` | 76% righe, **25% funzioni** | E' dove si legge un allarme alle tre di notte | 10 test: fatti dell'esecuzione, assenza/ripresa, ping di avvio, segna-come-letta, download del payload, permessi |

### Gate contro le regressioni future

```bash
make cov       # backend: fallisce sotto l'88% (attuale 90,4%)
make fe-cov    # frontend: soglie in vite.config.ts (statements 85, branches 78)
```

Sono **pavimenti, non obiettivi**: si alzano quando la copertura sale, non si
abbassano per far passare una modifica. I test sono esclusi dalla propria misura
(gonfiavano il totale del frontend di dieci punti).

### Quello che resta scoperto, consapevolmente

- `app/db/session.py` e `sync_session.py` (81%/71%): le factory delle sessioni
  non usate dai test (`ingest_session` viene esercitata, le altre no).
- `app/api/v1/presets.py`, `users.py`, `groups.py` restano fra il 73% e l'89%: i
  rami non coperti sono varianti di errore su percorsi gia' verificati.
- `ChannelsPage.tsx` (60%) e `UsersPage.tsx` (77%) sono le due pagine piu' grosse
  del frontend: coperte nei percorsi principali, non in ogni variante di form.

---

## Verifica 3 — revisione pre-staging (2026-09-09)

Passata di revisione completa su tutto il repository (backend, frontend, job,
deploy, documentazione) con l'obiettivo di consegnare per lo staging, piu il
controllo che i piani in `docs/` e `.planning/` corrispondano al codice.

**Stato di partenza:** tutti i gate erano verdi (619 test backend, 163 frontend,
`fmt-check`/`lint`/`types`/`fe-lint`/`fe-build` puliti). I difetti sotto erano
tutti **latenti**: nessuno di essi rompeva un test esistente, e il piu grave non
si vede affatto finche non passa un giorno con un payload offloaded in archivio.

### D1 — `purge_orphan_objects` cancellava i payload delle notifiche vive (perdita di dati)

`app/tasks/maintenance.py` leggeva l'insieme delle `storage_key` note da
`sync_session_factory()`, cioe da una sessione **senza `app.tenant_id`**.
`notifications` ha `FORCE ROW LEVEL SECURITY` e il ruolo `notifyhub_app` non ha
`BYPASSRLS`: quella SELECT non da errore, torna **zero righe**. L'insieme delle
chiavi note era quindi vuoto per costruzione e ogni oggetto del bucket piu
vecchio di 24h risultava orfano.

Effetto reale, ogni notte alle 04:00: cancellazione da MinIO di **tutti** i
payload offloaded (>1MB) piu vecchi di un giorno, con le righe `notifications`
ancora al loro posto e `GET /notifications/{id}/content` rotto per sempre.
Nessun errore nei log: il job registrava `purge_orphan_objects_done` con un
contatore alto e si dichiarava riuscito.

Lo stesso file conteneva gia la spiegazione del perche non si puo fare, nel
docstring di `recompute_tenant_usage`. Corretto iterando i tenant come tutti
gli altri job. Il test aggiunto, eseguito contro la vecchia implementazione,
fallisce cancellando 3 oggetti su 3.

### D2 — `Content-Length` sbagliato sul download di un payload normalizzato

`GET /notifications/{id}/content` dichiarava `Content-Length: content_size`, che
e la dimensione del corpo **originale**. Per un payload `inline` normalizzato
(UTF-8 non valido sostituito con U+FFFD, byte NUL rimossi — spec 6.2) i byte
inviati sono di piu: 10 byte in ingresso diventano 12 in uscita. Il client
tronca la risposta o la rifiuta. Ora la lunghezza e quella dei byte inviati.

### D3 — un `viewer` poteva marcare come letta, verificata e cancellare

`PATCH /notifications/{id}`, `POST /notifications/bulk-read` e
`DELETE /notifications/{id}` passavano da `current_claims` con
`assert_group_access(write=False)`: un `viewer`, che per spec ha accesso in sola
lettura, poteva modificare lo stato di qualunque notifica dei gruppi che gli
sono visibili. Ora richiedono `require_member` e il controllo di gruppo col
metro della scrittura. E anche il criterio 2 della fase 2 di
`.planning/ROADMAP.md`, che era dato per non implementato.

### D4 — il rate limit del login era di fatto per-email, non per (email, IP)

`login` leggeva `request.client.host` direttamente. Dietro il reverse proxy del
deploy standard quell'indirizzo e quello di nginx per **ogni** client: la chiave
`login_attempts:{email}:{ip}` si riduceva alla sola email e 10 tentativi
sbagliati bastavano a bloccare per 15 minuti un account noto — esattamente
l'attacco che la chiave composta doveva impedire, e che il commento nel codice
dichiarava di impedire. La risoluzione dell'IP con trusted proxy esisteva solo
nell'ingestion: e stata estratta in `app/api/deps.py:client_ip` e ora la usano
entrambi.

### D5 — un'eccezione non-HTTP nel worker lasciava la delivery bloccata per sempre

`send_webhook_sync` intercettava solo `httpx.HTTPError`. Qualunque altra
eccezione (`httpx.InvalidURL` su un `webhook_url` malformato, un errore di
serializzazione del payload) uscisse da `dispatch_delivery` lasciava la riga in
`sending`: `reconcile_deliveries` la riporta a `failed` dopo 10 minuti, la
riaccoda, si rompe di nuovo, per sempre, senza mai arrivare a `dead` e senza mai
contare un tentativo. Il gestore d'errore stesso poteva poi sollevare
`IndexError` (`webhook_url.split("/")[2]` su una stringa senza doppio slash).
Ora un guasto qualunque diventa un tentativo fallito, e l'host per il log si
estrae con `urlsplit` (il path di un webhook Slack **e** il segreto e non va
mai nei log).

### D6 — `FOR UPDATE` sul tenant a ogni ingestion, anche senza quote

`enforce_tenant_quotas` prendeva sempre un lock di riga sul tenant. Quel lock
serializza **tutte** le ingestion di quel tenant per la durata della
transazione, e veniva preso anche con entrambe le quote a `NULL`, cioe nella
configurazione di default, dove non c'e niente da proteggere. Ora si legge
prima se una quota esiste e il lock si prende solo in quel caso.

### D7 — filtri di stato mai implementati (fasi 3 e 4 di `.planning/ROADMAP.md`)

Il filtro `verified` non esisteva ne nell'API ne nella UI, e il parametro
`status` veniva letto dall'URL dalla pagina notifiche senza che nessun controllo
lo scrivesse: era cablatura morta. Aggiunti `verified` a
`GET /notifications` e a `POST /notifications/bulk-read` (combinabile con
`status`, sono due dimensioni indipendenti) e i due select corrispondenti nella
toolbar, con lo stato nell'URL come gli altri filtri.

### Pulizie

`CRON_LOOKBACK_DAYS` in `surveillance.py` (costante non usata, con un commento
che descriveva una protezione inesistente — quel caso e comunque coperto perche
`CroniterBadDateError` deriva da `ValueError`); parametri morti
`_synthetic_notification(group_name=...)` e `_reference_instant(schedule)`;
`except (ClientError, BotoCoreError, Exception)` in `readiness.py`, dove i primi
due termini non hanno effetto; messaggio del 415 dell'ingestion, che elencava
solo `text/plain` mentre l'endpoint accetta anche
`application/x-www-form-urlencoded` e l'assenza di Content-Type.

### Test aggiunti

| File | Test | Dimostra |
|---|---|---|
| `tests/integration/test_review_staging.py` | `una_lettura_senza_contesto_di_tenant_non_vede_nessuna_storage_key` | il meccanismo di D1 isolato: RLS forzata torna zero righe, non un errore |
| | `purge_orphan_objects_non_cancella_i_payload_delle_notifiche_vive` | D1: l'orfano vero se ne va, il payload di una notifica in elenco resta |
| | `le_quote_illimitate_non_serializzano_l_ingestion` | D6: con quote NULL una seconda transazione riesce a bloccare la riga tenant (`FOR UPDATE NOWAIT`) |
| | `con_una_quota_configurata_il_lock_resta` | D6, l'altra meta: con una quota il lock c'e ancora |
| `tests/e2e/test_review_staging.py` | `content_length_descrive_i_byte_inviati_non_il_corpo_originale` | D2 |
| | `viewer_non_puo_marcare_letta_ne_verificata` | D3: 403 su PATCH/bulk-read/DELETE, 200 in lettura, stato invariato |
| | `filtro_verified_indipendente_da_status` | D7: le due dimensioni si combinano |
| | `bulk_read_rispetta_il_filtro_verified` | D7: "segna tutte come lette" non tocca cio che il filtro esclude |
| | `rate_limit_del_login_separato_per_ip_dietro_un_proxy_fidato` | D4 |
| | `content_type_non_supportato_dice_quali_sono_accettati` | messaggio del 415 |
| `tests/unit/test_review_staging.py` | `client_ip_*` (3 test) | D4: X-Forwarded-For solo da un proxy dichiarato |
| | `send_webhook_sync_non_lascia_uscire_eccezioni_non_http` | D5 |
| | `host_of_non_solleva_su_url_malformato_e_non_rivela_il_path` | D5, gestore d'errore |
| `frontend/.../notifications.test.tsx` | `i_filtri_di_stato_e_verifica_finiscono_nell_URL` | D7 lato UI |
| | `segna_tutte_come_lette_non_tocca_cio_che_il_filtro_verifica_esclude` | D7, corpo della bulk-read |

### Gate dopo la passata

- Backend: `fmt-check`, `lint`, `types` puliti. **634 test passati** (da 619),
  copertura **90,55%** (soglia 88%).
- Frontend: `fe-lint` a zero warning, **165 test** (da 163), `fe-build` pulito,
  soglie di copertura rispettate (87,6 / 80,1).
- `scripts/smoke.sh` sullo stack containerizzato completo: vedi sotto.

---

## Verifica 5 — 2026-09-15 (receiver, crontab e attese non rispettate)

Richiesta: verificare le impostazioni dei receiver rispetto ai crontab, ai
ritardi tollerati e alla segnalazione quando la notifica non arriva entro il
tempo previsto.

### Difetti trovati

| # | Dove | Difetto | Effetto |
|---|---|---|---|
| S1 | `app/services/surveillance.py` | La scadenza si calcolava sulle occorrenze cron **a partire da adesso**, non dall'ultimo invio | Con una tolleranza piu' lunga del periodo del cron (`0 * * * *` + 2 ore di grazia) la scadenza si spostava in avanti a ogni giro del job: un receiver fermo da tre giorni **non veniva mai segnalato**. Ora la scadenza e' la prima occorrenza **successiva** al riferimento, piu' la tolleranza |
| S2 | `app/services/surveillance.py` | `validate_cron` accettava espressioni sintatticamente valide che non scattano mai (es. `0 0 30 2 *`) | Sorveglianza accesa e muta per sempre: il receiver risultava "sorvegliato" e nessuna assenza era segnalabile. Ora la validazione prova a calcolare la prima occorrenza e rifiuta l'espressione. Il frontend rifiuta esattamente le stesse espressioni |
| S3 | `app/api/v1/receivers.py` | Riattivando un receiver disabilitato la finestra di attesa non ripartiva | Il tempo passato da spento contava come ritardo: **allarme immediato** alla riattivazione, prima ancora che il job avesse la possibilita' di inviare. Ora `expected_since` riparte da adesso e `missing_alerted_at` si azzera |

Il riferimento da cui si conta e' ora uno solo e dichiarato:
`max(last_notification_at, expected_since)`, documentato in
`docs/notifyhub-spec.md` §4.2 insieme ai casi in cui la finestra riparte
(sorveglianza accesa, spenta e riaccesa, receiver riattivato) e al
comportamento sui cambi d'ora.

### Test aggiunti

21 test (`tests/unit/test_surveillance.py`, `tests/integration/test_surveillance_job.py`,
`tests/e2e/test_expected_schedule_api.py`), fra cui il caso di S1 con tolleranza
piu' lunga del periodo (una sola notifica di assenza, non zero e non una per
occorrenza persa), il cron che non scatta mai (S2) e il ciclo
disabilita→riattiva (S3). `docs/OPERAZIONI.md` (job 9) ha ora la diagnostica e
il runbook SQL per i due casi.

---

## Verifica 6 — 2026-09-15 (deep review del frontend)

Richiesta: stile non uniforme, spazio della pagina sfruttato male, corpi del
testo incoerenti, nessun riscontro quando si salva, nessuna evidenza di quali
campi siano obbligatori. Passata su **tutte** le sezioni.

### Il problema di fondo

Ogni pagina era stata scritta da sola: dimensioni del testo decise caso per
caso (da 11px a 28px senza scala), `style={{ }}` in linea per le distanze,
quattro modi di formattare una data, tre modi di dire "sto salvando". Non era
un problema estetico: **dopo aver cambiato un valore non si sapeva se fosse
stato salvato**, perche' l'unico segnale era che il campo tornava al valore del
server — cioe' nessun segnale, se il valore era gia' quello.

### Cosa e' stato introdotto

| Pezzo | File | A cosa serve |
|---|---|---|
| Token di stile | `styles.css` | Una sola scala tipografica (`--text-xs` … `--text-2xl`), una sola scala di spaziature, larghezze massime dichiarate (`--content-max`, `--prose-max`). Nessuna dimensione decisa nella pagina |
| Avvisi di esito | `hooks/useToast.tsx` | Riscontro immediato di ogni scrittura, `role="status"` in una regione `aria-live`, chiudibile, scade da solo |
| `useAction` | `hooks/useAction.ts` | Il giro che fa ogni scrittura: "in corso", errore tipizzato che **resta in linea**, avviso di esito. Sostituisce il `try/catch` + `setError` copiato in ogni componente |
| `SaveIndicator` | `components/SaveIndicator.tsx` | "Salvato ✓" accanto al controllo che si e' toccato, per le modifiche in riga (ruoli, soglie dei canali) dove l'avviso in basso e' lontano dal punto in cui si e' agito |
| `Field` + `RequiredLegend` + `fieldAria` | `components/Field.tsx` | Etichetta, obbligatorio/facoltativo, suggerimento, errore: sempre nello stesso ordine e con gli stessi id. `aria-describedby`/`aria-invalid` collegati |
| `Detail` | `components/Detail.tsx` | Coppia etichetta/valore nelle viste di sola lettura, dentro una griglia |
| `Modal` | `components/Modal.tsx` | I moduli di modifica compaiono dove si e' premuto "Modifica", non in fondo alla pagina. Escape, fuoco al primo campo, Tab che gira dentro |
| `lib/format.ts` | — | Una sola formattazione per date, ore, byte, ruoli, stati |

L'asterisco dei campi obbligatori e il "(facoltativo)" li mette il **CSS**
(`.is-required::after`, `.is-optional::after`): dentro l'etichetta finirebbero
nel nome accessibile del campo, che diventerebbe "Email \*".

### Difetti chiusi, per asse

| Asse | Prima | Ora |
|---|---|---|
| Riscontro di persistenza | Nessuno, in nessuna sezione | Avviso su ogni scrittura + indicatore in riga dove la modifica e' in riga (utenze, canali, preset, regole) |
| Obbligatorio / facoltativo | Nessuna indicazione: lo diceva il 422 del server | Marcato su ogni modulo principale, con legenda una volta per modulo |
| Validazione lato client | Solo su cron e soglia di durata del receiver | Anche: nome del receiver e del preset, pattern delle regole, password dell'invito (lunghezza **e** ripetizione), con l'errore legato al campo |
| Uso dello spazio | Una colonna stretta di `<p>Etichetta: valore</p>`, moduli in colonna singola su schermi larghi | `detail-grid` e `form-grid` che riempiono la larghezza disponibile, filtri in una barra sola, moduli di creazione richiudibili |
| Tipografia | Dimensioni decise pagina per pagina | Scala unica; nessuna dimensione fuori dalla scala |
| Azioni distruttive | "Rigenera slug" ed "Elimina regola" partivano al primo click | Conferma esplicita che dice **cosa si rompe** (i job che usano il vecchio slug, i receiver che usano il preset) |
| Date | Quattro formattazioni diverse | Una, in `lib/format.ts`; un valore assente e' "—", non "Invalid Date" |
| Stili in linea | 6 `style={{ }}` sparsi | Zero |

### Funzioni mancanti trovate strada facendo

- **Attiva/disabilita receiver**: l'API lo permette e la pagina mostrava
  "disabilitato" con il conteggio delle richieste rifiutate, ma non c'era nessun
  modo di riattivarlo dall'interfaccia. Aggiunto, con la conferma che spiega che
  alla riattivazione la finestra di sorveglianza riparte da adesso (il
  comportamento corretto dopo S3).
- **Azzera i filtri** su notifiche e audit: con sei filtri nell'URL, un elenco
  vuoto costringeva a ricontrollare una tendina alla volta.
- **Ripeti la password** nell'accettazione dell'invito: una battitura sbagliata
  chiudeva fuori dall'account appena attivato.

### Test

| File | Cosa dimostra |
|---|---|
| `components/__tests__/Field.test.tsx` | L'asterisco non entra nel nome accessibile; suggerimento ed errore sono legati al campo; l'errore e' annunciato |
| `components/__tests__/Modal.test.tsx` | Fuoco al primo campo, Escape, click sullo sfondo, Tab che gira dentro |
| `hooks/__tests__/useAction.test.tsx` | Esito riuscito (avviso + "Salvato"), fallito (avviso **e** banner che resta), errore vecchio che sparisce al tentativo riuscito |
| `lib/__tests__/format.test.ts` | Valori assenti e date illeggibili diventano "—"; unita' di misura dei byte |
| `pages/__tests__/acceptInvite.test.tsx` | Password corta, password diverse, token mancante: nessuna chiamata all'API |
| `pages/__tests__/receiverDetail.test.tsx` | Conferma prima di rigenerare lo slug (annullare non chiama niente), disabilita/riattiva, riscontro del salvataggio, nome vuoto rifiutato con `aria-invalid` |

Gli errori compaiono **due volte** di proposito — avviso che passa e banner che
resta — e i test lo asseriscono esplicitamente, per non farlo "correggere" a
una passata futura.

### Gate

- `make fe-lint`: zero warning. `make fe-build` (`tsc -b` + vite): pulito.
- **222 test** frontend in 31 file, 30 dei quali aggiunti in questa passata.
- `make fe-cov`: 87,9% righe / 82,2% rami, sopra le soglie di `vite.config.ts`
  (85 / 78).

### Coda della passata — consegne (2026-09-15)

La colonna "Notifica inoltrata" stampava l'anteprima del corpo come testo del
link: una riga di log lunga spingeva fuori vista le colonne che dicono com'e'
andata la consegna (stato, tentativi, codice HTTP). Ora e' un link **Apri**
come nell'elenco delle notifiche, con accanto i segnali che servono a
riconoscere la riga senza leggerne il testo: severity, receiver di origine,
data di ricezione.

Nella stessa sezione: la tendina degli stati elencava gli identificativi
dell'API (`dead`, `sent`) mentre la tabella diceva "Morta" e "Inviata"
(`statusLabel` ora e' una sola), e mancava l'azzeramento dei filtri presente
nelle altre sezioni. 4 test aggiunti (226 in totale): il corpo che non compare,
la riga che resta riconoscibile, le parole della tendina, il filtro che si
azzera.

Seconda passata sulla stessa tabella: la severity stava dentro la cella della
notifica, in mezzo al testo. Ora ha la sua colonna ed e' la prima, come
nell'elenco delle notifiche — le severity si scorrono in verticale invece di
cercarle dentro una riga di testo — e la data di ricezione ha la colonna
"Ricevuta" con giorno e ora su due righe, sempre come nell'elenco. 2 test: la
posizione del badge (prima cella, non dentro la seconda) e la colonna della
data.

### Audit: dove è avvenuto il fatto (2026-09-15)

Le due tabelle dell'audit dicevano *cosa* e *chi*, non *dove*: "receiver /
Backup notturno" non identifica niente se tre gruppi hanno un receiver con
quel nome, e "severity_rule / disco pieno" non dice su quale receiver la
regola sia stata aggiunta. Aggiunta la colonna **Gruppo / Receiver**, con il
receiver che e' un collegamento alla sua pagina.

La posizione **non** viene congelata nell'evento: `app/services/audit_location.py`
la risolve in lettura seguendo le chiavi esterne da `resource_id`, quindi vale
anche per gli eventi gia' in tabella. Copre tutto cio' che vive sotto un
receiver (`receiver`, `notification`, `severity_rule`,
`receiver_severity_preset`, `receiver_channel_override`), i gruppi
(`group`, `group_channel_binding`) e il `bulk-read`, che non ha una risorsa
singola e porta il proprio ambito nei filtri dentro `context`. Query in blocco
(una per tipo di risorsa, piu' due), a chunk di mille id per reggere anche
l'export da 50.000 righe, che ora ha le stesse due colonne. Se la risorsa e'
stata cancellata i campi restano nulli e la tabella mostra un trattino: la riga
di audit sopravvive alla risorsa e inventarne la posizione sarebbe peggio che
non dirla.

In «Letture e verifiche», due altre correzioni:

- la colonna "Notifica" stampava l'anteprima del corpo come testo del link →
  ora e' **Apri**, come nell'elenco delle notifiche e nelle consegne;
- la **ricerca per id notifica** era un campo senza sorgente: nessuna schermata
  espone gli uuid, quindi non c'era modo di riempirlo. Rimossa. Allo storico di
  una singola notifica si arriva dal suo dettaglio, con «Chi l'ha letta o
  verificata» (owner e admin: agli altri l'audit risponde 403); la vista
  filtrata si dichiara in cima e si lascia con «Mostrale tutte».

8 test backend (722 in totale) e 6 frontend (234): gruppo del receiver, regola
di severity, notifica letta, bulk-read, risorsa cancellata, export CSV, evento
di gruppo, legame gruppo-canale; lato UI la colonna e i suoi collegamenti, il
trattino, il link "Apri", il filtro che arriva dall'URL e si toglie, il
collegamento assente per il member.

