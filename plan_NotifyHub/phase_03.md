# Fase 2 — Nucleo trasversale: configurazione, log, cifratura, errori, metriche

> **Intent:** costruire i servizi trasversali su cui poggia tutto il resto, in modo che nessuna fase successiva debba inventarsi un formato di errore, un modo di loggare o un modo di cifrare.
> **Shippable alone?** si — l'applicazione acquisisce log strutturati, gestione uniforme degli errori, endpoint di prontezza e metriche, senza logica di dominio.
> **Preconditions:** fase 1 DONE.

Fonti autoritative: `notifyhub-spec.md` sezione 9 (formato degli errori), sezione 10.3 (segreti), sezione 10.4 (superficie esposta), sezione 13 (variabili e healthcheck).

---

## Sub-phases

### 2.1 Configurazione tipizzata

- **Model:** Sonnet
- **Files:** `backend/app/core/config.py` (nuovo).
- **Pattern:** `pydantic_settings.BaseSettings` con singleton memoizzato. **Nessun modulo legge `os.environ` direttamente**: tutti passano da qui. Se in una fase successiva vedi `os.getenv`, e un errore.
- **Change:** definisci `class Settings(BaseSettings)` con un campo tipizzato per ogni variabile elencata in `.env.example` (fase 0 sotto-fase 0.3), stessi nomi in minuscolo. Vincoli aggiuntivi:
  - `notifyhub_secret_key: str` con `min_length=32`. Chiave piu corta significa cifratura debole: la validazione deve fallire all'avvio, non a runtime.
  - `notifyhub_inline_max_bytes: int = 1048576` e `notifyhub_hard_max_body_bytes: int = 20971520`.
  - `cors_origins: list[str]` con parsing da stringa separata da virgole.
  - `trusted_proxies: list[str]` con lo stesso parsing, vuoto per default.
  - `notifyhub_public_base_url: str` — origine pubblica della dashboard. Serve a costruire i link di invito (fase 3) e i collegamenti dentro i messaggi inoltrati (fase 6). Nessun modulo deve comporre URL assolute in altro modo.
  - `webhook_host_allowlist: list[str]` — host verso cui e ammesso configurare un DeliveryChannel, con lo stesso parsing da stringa separata da virgole. Default `hooks.slack.com,chat.googleapis.com`. E la difesa contro l'uso di NotifyHub come strumento di richieste verso host arbitrari.
  - `allow_public_registration: bool = False`. Il default e `False`: se lo trovi `True`, e un errore (specifica sezione 10.2).
  - `smtp_host: str | None = None` e gli altri campi SMTP tutti opzionali.
  - `model_config = SettingsConfigDict(env_file=os.environ.get("ENV_FILE", ".env"), extra="forbid")`. `extra="forbid"` fa fallire l'avvio se nell'ambiente compare una variabile `NOTIFYHUB_*` non prevista: e la difesa contro l'introduzione silenziosa di configurazione non pianificata.
  Esporta `@lru_cache def get_settings() -> Settings`.
  Aggiungi una proprieta calcolata `smtp_enabled: bool` che vale `True` solo se `smtp_host` e `smtp_from` sono entrambi valorizzati.
- **Test strategy:** test unitari con `monkeypatch` sull'ambiente e `get_settings.cache_clear()` fra un test e l'altro.
- **Unit tests:** in `backend/tests/unit/test_config.py`:
  `test_chiave_troppo_corta_rifiutata` — con `NOTIFYHUB_SECRET_KEY` di 10 caratteri, `Settings()` solleva `ValidationError`. Test di percorso negativo: fallisce se qualcuno toglie il vincolo di lunghezza.
  `test_registrazione_pubblica_disattiva_per_default` — senza la variabile, `allow_public_registration is False`.
  `test_smtp_disabilitato_se_incompleto` — con solo `SMTP_HOST` valorizzato, `smtp_enabled is False`.
  `test_cors_origins_parsate` — `CORS_ORIGINS="http://a,http://b"` produce una lista di due elementi.
- **e2e tests:** nessuno.
- **Done:** `make types` e `make lint` verdi; i quattro test passano.

### 2.2 Log strutturati e identificativo di richiesta

- **Model:** Sonnet
- **Files:** `backend/app/core/logging.py` (nuovo), `backend/app/main.py` (modificato).
- **Insertion point:** in `main.py`, la chiamata a `configure_logging()` va come **prima istruzione** di `create_app()`, prima della costruzione di `FastAPI(...)`. Il middleware si registra subito dopo la costruzione dell'app, prima del commento sentinella `# ROUTERS:`.
- **Pattern:** `structlog` con renderer JSON, piu un middleware ASGI che genera o propaga `X-Request-Id` e lo lega al contesto del logger.
- **Change:**
  - `configure_logging()` configura structlog con processori: merge del contesto, aggiunta di livello e timestamp ISO 8601 in UTC, `JSONRenderer`. Livello da `settings.log_level`.
  - `RequestIdMiddleware` (`BaseHTTPMiddleware`): legge `X-Request-Id` dalla richiesta, se assente ne genera uno con `uuid4`, lo lega con `structlog.contextvars.bind_contextvars(request_id=...)`, lo restituisce nell'header di risposta e ripulisce il contesto al termine.
  - Esporta `get_logger(name)` come unico modo di ottenere un logger.
  - **Filtro dei segreti**: aggiungi un processore `redact_secrets` che, per ogni valore stringa dell'evento, sostituisce con `"[redacted]"` il contenuto delle chiavi il cui nome contiene `password`, `token`, `secret`, `webhook`, `authorization`. E la difesa meccanica dell'invariante I-6.
- **Test strategy:** cattura degli eventi con `structlog.testing.capture_logs`.
- **Unit tests:** in `backend/tests/unit/test_logging.py`:
  `test_segreti_oscurati` — logga `logger.info("x", webhook_url="https://hooks.slack.com/AAA", password="p")` e asserisce che nell'evento catturato nessuno dei due valori originali compaia e che entrambi valgano `"[redacted]"`. Test di percorso negativo: fallisce se il processore viene rimosso.
  `test_log_e_json_valido` — l'output renderizzato e deserializzabile con `json.loads` e contiene le chiavi `event`, `level`, `timestamp`.
- **e2e tests:** `T-CORE1` in `backend/tests/e2e/test_request_id.py::test_request_id_propagato` — `GET /healthz` con header `X-Request-Id: abc-123` restituisce lo stesso valore nell'header di risposta; senza header in ingresso, la risposta ne contiene comunque uno non vuoto.
- **Done:** `make gates` verde; `T-SCAF1` resta verde.

### 2.3 Cifratura dei webhook

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/core/crypto.py` (nuovo).
- **Pattern:** AES-GCM da `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, chiave derivata dalla configurazione, nonce casuale a 12 byte concatenato davanti al ciphertext.
- **Change:** due sole funzioni pubbliche:
  ```python
  def encrypt_secret(plaintext: str) -> bytes
  def decrypt_secret(blob: bytes) -> str
  ```
  - la chiave e `sha256(settings.notifyhub_secret_key.encode()).digest()`, cioe 32 byte: la variabile d'ambiente puo essere una passphrase leggibile;
  - il nonce e generato con `os.urandom(12)` a ogni cifratura e il formato persistito e `nonce || ciphertext || tag` (il tag lo accoda gia AESGCM);
  - `decrypt_secret` su un blob manomesso deve sollevare `cryptography.exceptions.InvalidTag`, non restituire dati: non catturare l'eccezione qui.
  Aggiungi una terza funzione `mask_webhook(url: str) -> str` che produce l'hint mostrato dall'API: schema e host integrali, path sostituito da `/.../` piu gli ultimi 4 caratteri, ad esempio `https://hooks.slack.com/.../AB12`. E l'unica rappresentazione di un webhook che puo uscire dall'applicazione (invariante I-6).
- **Test strategy:** test unitari puri, nessuna dipendenza esterna.
- **Unit tests:** in `backend/tests/unit/test_crypto.py`:
  `test_roundtrip` — `decrypt_secret(encrypt_secret(s)) == s` per una URL di webhook realistica.
  `test_nonce_diverso_ogni_volta` — due cifrature dello stesso testo producono blob diversi. Fallisce se qualcuno fissa il nonce, che e l'errore classico su GCM.
  `test_manomissione_rilevata` — capovolto un bit del blob, `decrypt_secret` solleva `InvalidTag`. Test di percorso negativo.
  `test_mask_webhook_non_rivela_il_segreto` — `mask_webhook("https://hooks.slack.com/services/T000/B000/XYZSEGRETO")` non contiene la sottostringa `XYZSEGRETO` per intero e termina con gli ultimi 4 caratteri.
- **e2e tests:** nessuno (nessun endpoint ancora).
- **Done:** i quattro test passano; `make gates` verde.

### 2.4 Errori uniformi RFC 7807

- **Model:** Sonnet
- **Files:** `backend/app/core/errors.py` (nuovo), `backend/app/main.py` (modificato).
- **Insertion point:** in `create_app()`, la registrazione degli exception handler va dopo il middleware di 2.2 e prima del commento sentinella `# ROUTERS:`.
- **Pattern:** una sola funzione costruisce il corpo; tutti gli handler la usano (decisione D10).
- **Change:**
  - `class Problem(Exception)` con attributi `status`, `type`, `title`, `detail`, `extra: dict`. Le eccezioni di dominio delle fasi successive sottoclassano questa.
  - `def problem_response(p: Problem) -> JSONResponse` che serializza `{"type", "title", "status", "detail", **extra}` con media type `application/problem+json`.
  - Handler registrati in `create_app`: per `Problem`, per `RequestValidationError` (che diventa `422` con `type=/problems/validation-error` e l'elenco degli errori in `extra["errors"]`), per `HTTPException` di Starlette, e un handler generico per `Exception` che logga l'eccezione completa e restituisce un `500` con `detail` fisso `"errore interno"`. **Il corpo del 500 non contiene mai il messaggio dell'eccezione**: potrebbe includere un segreto (invariante I-6).
  - Un registro di costanti `PROBLEM_TYPES` con le stringhe usate nel sistema, fra cui `/problems/not-found`, `/problems/validation-error`, `/problems/last-owner`, `/problems/quota-exceeded`, `/problems/rate-limited`, `/problems/payload-too-large`, `/problems/conflict`, `/problems/forbidden`, `/problems/unauthorized`, `/problems/storage-unavailable`.
  - **Costante `INGEST_NOT_FOUND_BODY`**: il corpo esatto e immutabile restituito dall'ingestion nei tre casi indistinguibili dell'invariante I-2. Definiscilo qui, come dizionario congelato, cosi esiste un solo punto di verita e la fase 5 non puo costruirne varianti.
- **Test strategy:** test e2e su rotte finte registrate solo nel test, piu un test unitario sulla costante.
- **Unit tests:** `backend/tests/unit/test_errors.py::test_corpo_404_ingest_e_costante` — asserisce che `INGEST_NOT_FOUND_BODY` sia un mapping immutabile e che non contenga le parole `slug`, `disabled`, `receiver`, `tenant`: il corpo non deve suggerire quale dei tre casi si sia verificato.
- **e2e tests:** `T-CORE2` in `backend/tests/e2e/test_errors.py::test_problem_json_su_validazione` — una richiesta non valida verso una rotta di prova restituisce `422`, `content-type: application/problem+json` e un corpo con le chiavi `type`, `title`, `status`.
  `T-CORE3` `test_500_non_espone_il_messaggio` — una rotta di prova che solleva `RuntimeError("segreto-xyz")` produce `500` il cui corpo **non** contiene `segreto-xyz`. Test di percorso negativo.
- **Done:** `make gates` verde; `T-SCAF2` resta verde.

### 2.5 Metriche Prometheus su porta interna

- **Model:** Haiku
- **Files:** `backend/app/core/metrics.py` (nuovo), `backend/app/main.py` (modificato).
- **Insertion point:** in `create_app()`, subito prima del commento sentinella `# ROUTERS:`.
- **Pattern:** un registro Prometheus dedicato e una seconda applicazione ASGI montata su una porta separata, non instradata da nginx (specifica sezione 10.4).
- **Change:**
  - dichiara i collettori usati dall'intero sistema, tutti in questo modulo e da nessuna altra parte:
    `ingest_requests_total` (Counter, label `outcome` fra `created`, `replayed`, `not_found`, `too_large`, `rate_limited`, `error`),
    `ingest_body_bytes` (Histogram),
    `deliveries_total` (Counter, label `outcome` fra `sent`, `failed`, `dead`),
    `delivery_latency_seconds` (Histogram),
    `pending_object_deletions_backlog` (Gauge),
    `http_request_duration_seconds` (Histogram, label `route` e `method`).
  - esporta `metrics_app` costruita con `prometheus_client.make_asgi_app()` sul registro dichiarato;
  - in `create_app`, monta `metrics_app` su `/metrics`. **La porta 9100 e ottenuta a livello di deploy** eseguendo un secondo processo uvicorn: in fase 10 sotto-fase 10.3 il servizio `api` avvia entrambe. Non pubblicare `/metrics` attraverso nginx.
- **Test strategy:** verifica dell'esposizione, non dei valori.
- **Unit tests:** nessuno.
- **e2e tests:** `T-CORE4` in `backend/tests/e2e/test_metrics.py::test_metriche_esposte` — `GET /metrics` restituisce 200 e il corpo contiene la stringa `ingest_requests_total`.
- **Done:** `make gates` verde.

### 2.6 Endpoint di prontezza

- **Model:** Sonnet
- **Files:** `backend/app/api/health.py` (nuovo), `backend/app/main.py` (modificato), `backend/app/services/storage.py` (nuovo, solo il client).
- **Insertion point:** il router si registra in `create_app` immediatamente prima del commento sentinella `# ROUTERS:`. Sposta `/healthz` dalla definizione inline di fase 0 dentro questo router, cosi i due endpoint stanno insieme.
- **Pattern:** liveness senza dipendenze, readiness con verifica delle tre dipendenze in parallelo e timeout breve.
- **Change:**
  - `GET /healthz` invariato: `{"status": "ok"}`, nessuna dipendenza.
  - `GET /readyz` verifica in parallelo con `asyncio.gather`: `SELECT 1` su `engine_app`, `PING` su Redis, `head_bucket` su MinIO. Timeout complessivo 3 secondi. Risposta `200` con `{"postgres": true, "redis": true, "storage": true}` se tutte passano, `503` con lo stesso dizionario e i falsi valorizzati altrimenti.
  - in `app/services/storage.py` crea per ora **solo** la funzione `get_s3_client()` che restituisce un client `aioboto3` configurato da `settings`, e `async def head_bucket() -> bool`. Il resto del servizio di storage arriva in fase 5 sotto-fase 5.5: non anticiparlo.
- **Test strategy:** il percorso felice contro i servizi di test; il percorso di errore forzando un endpoint S3 inesistente via monkeypatch.
- **Unit tests:** nessuno.
- **e2e tests:** `T-CORE5` in `backend/tests/integration/test_readyz.py::test_readyz_ok` (marker `integration`) — con lo stack di test attivo, `GET /readyz` restituisce 200 e tutti e tre i valori a `true`.
  `T-CORE6` `test_readyz_degradato` — con `NOTIFYHUB_S3_ENDPOINT` puntato a una porta chiusa, `GET /readyz` restituisce `503` e `storage` vale `false`, mentre `postgres` resta `true`. Test di percorso negativo: dimostra che la verifica e reale e non finta.
- **Done:** `make gates` verde con `T-CORE1` .. `T-CORE6`.

---

## Files touched (this phase)

- `backend/app/core/config.py` — creato — configurazione tipizzata, unico accesso all'ambiente
- `backend/app/core/logging.py` — creato — structlog JSON, middleware request id, oscuramento segreti
- `backend/app/core/crypto.py` — creato — AES-GCM e mascheramento webhook
- `backend/app/core/errors.py` — creato — RFC 7807, registro dei tipi, corpo costante del 404 di ingestion
- `backend/app/core/metrics.py` — creato — collettori Prometheus e app di esposizione
- `backend/app/api/health.py` — creato — `/healthz` e `/readyz`
- `backend/app/services/storage.py` — creato — solo client S3 e `head_bucket`
- `backend/app/main.py` — modificato — logging, middleware, handler, metriche, router di salute
- `backend/tests/unit/test_config.py`, `test_logging.py`, `test_crypto.py`, `test_errors.py` — creati
- `backend/tests/e2e/test_request_id.py`, `test_errors.py`, `test_metrics.py` — creati
- `backend/tests/integration/test_readyz.py` — creato

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** tutti i test delle fasi 0 e 1 restano verdi, in particolare `T-RLS3` .. `T-RLS9`.

## Phase done criterion

`make gates` verde. `GET /readyz` distingue davvero uno stack sano da uno degradato (`T-CORE6`). Nessun segreto raggiunge i log (`test_segreti_oscurati`) ne il corpo di un errore 500 (`T-CORE3`). Esiste un solo punto nel codice che definisce il corpo del 404 di ingestion.
