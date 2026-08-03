# Fase 5 — Ingestion

> **Intent:** realizzare `POST /ingest/{slug}` completo: limiti, risoluzione dello slug senza contesto di tenant, lettura del corpo in streaming, normalizzazione, catena di severity, offload su MinIO, idempotenza.
> **Shippable alone?** si — al termine si inviano notifiche con `curl` e si ritrovano in tabella. L'inoltro verso Slack arriva in fase 6.
> **Preconditions:** fase 4 DONE.

Fonti autoritative: `notifyhub-spec.md` sezione 6.1 (contratto del modulo), 6.2 (modulo `http_raw` e normalizzazione), 6.3 (idempotenza), 6.5 (storage), sezione 7 (catena di severity), sezione 9.1 (codici di risposta), sezione 10.1 (sicurezza dell'endpoint).

Invarianti in gioco: **I-2** (404 indistinguibile), **I-3** (solo RE2), **I-7** (l'ingestion non fallisce mai per il contenuto).

---

## Sub-phases

### 5.1 Limiti di frequenza dell'ingestion

- **Model:** Sonnet
- **Files:** `backend/app/services/ratelimit.py` (modificato).
- **Insertion point:** in coda al modulo creato in fase 3 sotto-fase 3.4, sotto la funzione `sliding_window_hit`, che va **riusata e non riscritta**.
- **Pattern:** due contatori distinti, con chiavi separate, valutati in ordine.
- **Change:** aggiungi due funzioni sottili:
  ```python
  async def check_ip_limit(ip: str) -> RateLimitResult          # 300 richieste / 60 s, chiave "ingest:ip:{ip}"
  async def check_slug_limit(receiver_id: UUID, limit: int) -> RateLimitResult   # chiave "ingest:slug:{receiver_id}"
  ```
  Il limite per IP e una costante di modulo `IP_RATE_LIMIT = 300`, non una variabile d'ambiente: la specifica sezione 10.1 lo fissa e non e configurabile.
  `check_slug_limit` con `limit == 0` restituisce sempre `allowed=True`: e la semantica di "nessun limite per slug" della specifica. **Il limite per IP resta comunque applicato**: e il punto in cui la gente sbaglia.
  Aggiungi anche `async def bump_rejected_counter(receiver_id: UUID) -> None`, che incrementa `ingest:rejected:{receiver_id}` con TTL 86400 secondi, e `async def read_rejected_counter(receiver_id: UUID) -> int`. Servono alla diagnostica del receiver disabilitato (specifica sezione 9.1).
- **Test strategy:** integrazione contro il Redis di test, con chiavi ripulite dalla fixture di fase 3.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_ratelimit_ingest.py` (marker `integration`):
  `T-ING1` `test_limite_ip` — 300 chiamate consentite, la 301 rifiutata con `retry_after > 0`.
  `T-ING2` `test_limite_slug_zero_illimitato` — con `limit=0`, mille chiamate sono tutte consentite.
  `T-ING3` `test_contatore_rifiuti_con_scadenza` — dopo tre incrementi, la lettura restituisce 3 e il TTL della chiave e maggiore di zero.
- **Done:** i tre test passano.

### 5.2 Risoluzione dello slug e uniformita del 404

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/services/ingest_lookup.py` (nuovo).
- **Pattern:** una sola funzione che restituisce o il receiver risolto o `None`, senza mai spiegare perche. La spiegazione non deve esistere nemmeno come valore di ritorno, altrimenti prima o poi finisce nella risposta.
- **Change:**
  ```python
  async def resolve_slug(slug: str) -> ResolvedReceiver | None
  ```
  Apre `ingest_session()` (pool `notifyhub_ingest`, sola lettura su `receivers`, nessuna GUC), esegue **una sola query** che carica il receiver per slug insieme allo stato del tenant, e restituisce `None` in tutti e tre i casi: slug inesistente, `receiver.status == 'disabled'`, `tenant.status == 'suspended'`.

  Problema: il ruolo `notifyhub_ingest` ha `SELECT` solo su `receivers`, quindi non puo leggere `tenants` per conoscerne lo stato. Due sole soluzioni ammesse, scegli la prima:
  1. **denormalizza lo stato del tenant sul receiver** non e ammesso, introduce disallineamento;
  2. **estendi la GRANT** aggiungendo `SELECT (id, status)` su `tenants` al ruolo `notifyhub_ingest`, con una nuova migrazione `0004_grant_ingest_tenant_status.py`. `tenants` e fuori da RLS e la colonna `status` non e un segreto.
  Adotta la soluzione 2 e scrivi la migrazione. Se ti sembra che serva altro, **fermati e chiedi**.

  `ResolvedReceiver` e una dataclass con `id`, `tenant_id`, `group_id`, `max_body_bytes`, `rate_limit_per_min`, `default_severity`, `ingestion_module`. Nient'altro.

  Aggiungi nello stesso modulo:
  ```python
  async def respond_not_found(started_at: float) -> Response
  ```
  che attende fino a raggiungere un tempo minimo di risposta costante `NOT_FOUND_FLOOR_SECONDS = 0.025` e poi restituisce `INGEST_NOT_FOUND_BODY` (la costante definita in fase 2 sotto-fase 2.4) con status `404` e media type `application/problem+json`. Il pavimento temporale e cio che rende il 404 indistinguibile anche nei tempi, come richiede la specifica sezione 10.1: senza, il caso "slug inesistente" torna molto piu in fretta del caso "receiver disabilitato", che ha fatto una query in piu.
- **Test strategy:** i tre casi devono produrre risposte identiche; il confronto e sui byte del corpo e sulla varianza dei tempi.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_ingest_404.py` (i test finali girano dopo 5.7, ma il modulo si crea qui):
  `T-ING4` `test_tre_casi_stesso_corpo` — slug inesistente, receiver `disabled` e tenant `suspended` producono tre risposte con `status == 404` e `response.content` **byte-identico**. E il test dell'invariante I-2; fallisce se qualcuno aggiunge un dettaglio diagnostico al corpo.
  `T-ING5` `test_nessun_410_nel_sistema` — scansione dei sorgenti di `backend/app`: nessuna occorrenza di `410`. Test di conformita: la specifica ha eliminato quel codice e non deve rientrare.
  `T-ING6` `test_tempi_confrontabili` — venti chiamate per ciascuno dei tre casi; la differenza fra le mediane e inferiore a 15 ms e tutte le risposte superano il pavimento di 25 ms.
- **Done:** la migrazione `0004` applicata; `T-RLS7` va aggiornato per riflettere la GRANT aggiuntiva e resta verde.

### 5.3 Lettura del corpo, limite di dimensione, normalizzazione

- **Model:** Sonnet
- **Files:** `backend/app/services/body_reader.py` (nuovo).
- **Pattern:** buffer `tempfile.SpooledTemporaryFile(max_size=INLINE_MAX_BYTES)`: resta in RAM sotto la soglia, passa su disco sopra. Cosi un corpo da 20MB non occupa 20MB di heap per richiesta.
- **Change:**
  ```python
  async def read_body(request: Request, max_bytes: int) -> BodyResult
  ```
  Legge `request.stream()` a blocchi, contando i byte. **Appena il conteggio supera `max_bytes` interrompe la lettura** e solleva `Problem(413, "/problems/payload-too-large", ...)`: non si legge il resto e non si bufferizza il corpo intero per poi misurarlo.
  Se l'header `Content-Length` e presente e gia supera `max_bytes`, risponde `413` prima di leggere anche un solo byte.

  A lettura completata esegue la normalizzazione della specifica sezione 6.2, in questo ordine:
  1. `raw.decode("utf-8", errors="replace")`;
  2. rimozione di tutti i caratteri `\x00`;
  3. `normalized = True` se uno dei due passi ha cambiato qualcosa.

  `BodyResult` contiene: `raw_size: int` (i byte **originali**, non quelli della stringa normalizzata), `text: str`, `preview: str` (primi 4096 caratteri di `text`), `normalized: bool`, `spooled: SpooledTemporaryFile` (posizionato all'inizio, per l'eventuale caricamento su MinIO dei byte originali).

  > **Attenzione.** `content_size` in tabella e `raw_size`, non `len(text)`. Un carattere sostituito da `�` cambia la lunghezza della stringa ma non i byte ricevuti, e la dimensione riportata all'utente deve essere quella reale.
- **Test strategy:** unitari con un finto `Request` che espone uno `stream()` asincrono; nessuna rete.
- **Unit tests:** in `backend/tests/unit/test_body_reader.py`:
  `test_limite_interrompe_la_lettura` — con `max_bytes=100` e uno stream che produrrebbe 10.000 byte, viene sollevato `Problem` 413 e lo stream ha erogato meno di 1.000 byte. Test di percorso negativo che dimostra che la lettura si interrompe davvero.
  `test_content_length_anticipa_il_413` — con `Content-Length: 999999` e `max_bytes=100`, `Problem` 413 e lo stream non e stato consumato affatto.
  `test_byte_non_utf8_normalizzati` — corpo `b"ciao \xff mondo"` produce `normalized=True`, `text` contiene `�` e `raw_size == 13`.
  `test_byte_nul_rimossi` — corpo `b"a\x00b"` produce `text == "ab"`, `normalized=True`, `raw_size == 3`.
  `test_testo_pulito_non_marcato` — corpo ASCII normale produce `normalized=False` e `text` identico. Impedisce di marcare tutto come normalizzato.
  `test_preview_troncata_a_4096` — corpo di 10.000 caratteri produce `len(preview) == 4096`.
- **e2e tests:** nessuno in questa sotto-fase; il comportamento attraverso HTTP e coperto da `T-ING17` e `T-ING24` nella sotto-fase 5.7.
- **Done:** i sei test passano.

### 5.4 Catena di risoluzione della severity

- **Model:** Sonnet
- **Files:** `backend/app/services/severity.py` (modificato).
- **Insertion point:** in coda al modulo creato in fase 4 sotto-fase 4.3, riusando `evaluate_rules` e senza duplicarla.
- **Change:** aggiungi
  ```python
  async def resolve_severity(session, receiver, text, explicit_raw: str | None) -> SeverityDecision
  ```
  che applica esattamente la catena della specifica sezione 7:
  1. se `explicit_raw` e un valore valido dell'enum -> `(severity, source="explicit")`;
  2. se `explicit_raw` e presente ma non valido -> **non fallire**: logga a livello `info` con il valore ricevuto e prosegui al passo 2;
  3. regole del receiver abilitate, ordinate per `priority` crescente, valutate con `evaluate_rules` -> `(severity, source="rule", rule_id)`;
  4. altrimenti `(receiver.default_severity, source="receiver_default")`.
  `explicit_raw` arriva dall'header `X-Severity` oppure, se assente, dal parametro di query `severity`. Se sono presenti entrambi, vince l'header.
- **Unit tests:** in `backend/tests/unit/test_severity_chain.py`:
  `test_esplicita_vince_sulle_regole` — con una regola che darebbe `error` e header `X-Severity: debug`, il risultato e `debug` con `source=explicit`.
  `test_esplicita_non_valida_ignorata` — con `X-Severity: banana` e una regola che da `error`, il risultato e `error` con `source=rule` e **nessuna eccezione**. Test di percorso negativo dell'invariante I-7.
  `test_default_se_nessuna_regola` — nessuna regola corrisponde, il risultato e il default del receiver con `source=receiver_default`.
  `test_header_vince_su_query` — header `warning` e query `critical` danno `warning`.
- **e2e tests:** nessuno in questa sotto-fase; la catena attraverso HTTP e coperta da `T-ING14`, `T-ING15` e `T-ING16` nella sotto-fase 5.7.
- **Done:** i quattro test passano.

### 5.5 Servizio di storage inline e object

- **Model:** Sonnet
- **Files:** `backend/app/services/storage.py` (modificato).
- **Insertion point:** in coda al modulo creato in fase 2 sotto-fase 2.6, che finora contiene solo `get_s3_client` e `head_bucket`.
- **Pattern:** una funzione decide dove va il corpo; il chiamante non conosce MinIO.
- **Change:** aggiungi:
  ```python
  def build_storage_key(tenant_id: UUID, notification_id: UUID, received_at: datetime) -> str
  async def put_payload(key: str, spooled: SpooledTemporaryFile, size: int) -> None
  async def get_payload_stream(key: str) -> AsyncIterator[bytes]
  async def delete_payload(key: str) -> None
  ```
  `build_storage_key` produce esattamente `{tenant_id}/{yyyy}/{mm}/{dd}/{notification_id}.txt` come da specifica sezione 6.5. Il nome del bucket **non** fa parte della chiave: sta nella configurazione.
  `put_payload` carica i **byte originali** dallo spooled file, non il testo normalizzato: il download deve restituire cio che e stato inviato.
  `put_payload` su errore solleva `Problem(503, "/problems/storage-unavailable", ...)`.
  `get_payload_stream` restituisce un iteratore asincrono di blocchi da 64KB, per non caricare 20MB in memoria.
- **Test strategy:** integrazione contro il MinIO di test sulla porta 9002.
- **Unit tests:** `backend/tests/unit/test_storage_key.py::test_formato_chiave` — con valori noti la chiave e esattamente `<uuid>/2026/08/01/<uuid>.txt`. Fallisce se qualcuno cambia il formato, che romperebbe `purge_orphan_objects` in fase 8.
- **e2e tests:** in `backend/tests/integration/test_storage.py` (marker `integration`):
  `T-ING7` `test_put_e_get_roundtrip` — caricato un payload di 2MB, `get_payload_stream` restituisce gli stessi byte, confrontati per hash.
  `T-ING8` `test_delete_rimuove` — dopo `delete_payload`, un `head_object` sulla chiave fallisce.
  `T-ING9` `test_storage_non_disponibile` — con endpoint puntato a una porta chiusa, `put_payload` solleva `Problem` con status 503, non un errore generico. Test di percorso negativo.
- **Done:** i tre test passano.

### 5.6 Idempotenza su `X-Request-Id`

- **Model:** Sonnet
- **Files:** `backend/app/services/idempotency.py` (nuovo).
- **Pattern:** `SET NX EX` su Redis; la chiave contiene l'esito della prima elaborazione, cosi il replay puo restituire la stessa risposta.
- **Change:**
  ```python
  async def reserve(receiver_id: UUID, request_id: str) -> str | None
  async def store_result(receiver_id: UUID, request_id: str, payload: dict) -> None
  async def load_result(receiver_id: UUID, request_id: str) -> dict | None
  ```
  Chiave: `ingest:idem:{receiver_id}:{sha256(request_id)}`, finestra `IDEMPOTENCY_WINDOW_SECONDS = 300` come da specifica sezione 6.3.
  `reserve` esegue `SET chiave "pending" NX EX 300`: restituisce `None` se la prenotazione e riuscita (prima occorrenza), oppure il valore gia presente se la chiave esisteva.
  `store_result` sovrascrive il valore con il JSON dell'esito, mantenendo il TTL residuo.
  Se una prima richiesta trova la chiave in stato `pending` (elaborazione ancora in corso), il chiamante risponde `409` con `type=/problems/conflict`: e un caso raro e vale la pena renderlo esplicito invece di raddoppiare la notifica.
  Il valore di `X-Request-Id` non viene mai usato come chiave in chiaro: sempre l'hash. Un client potrebbe metterci dentro un segreto.
- **Test strategy:** integrazione contro Redis.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_idempotency.py` (marker `integration`):
  `T-ING10` `test_prima_occorrenza_prenota` — `reserve` restituisce `None`; la seconda chiamata restituisce `"pending"`.
  `T-ING11` `test_risultato_recuperabile` — dopo `store_result`, `load_result` restituisce il dizionario originale.
  `T-ING12` `test_finestra_scade` — con `freezegun` oltre i 300 secondi e la chiave scaduta in Redis, `reserve` prenota di nuovo. Se l'ambiente non consente di manipolare il TTL, esegui il test con una finestra ridotta iniettata come parametro, non con un `sleep`.
- **Done:** i tre test passano.

### 5.7 Endpoint di ingestion e modulo `http_raw`

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/ingestion/__init__.py` (nuovo), `backend/app/ingestion/registry.py` (nuovo), `backend/app/ingestion/http_raw.py` (nuovo), `backend/app/api/ingest.py` (nuovo), `backend/app/main.py` (modificato).

  > **Nota sulla struttura.** Questa e l'unica cartella nuova non prevista nell'albero dell'overview. E giustificata: la specifica sezione 6.1 definisce un registro di moduli di ingestion estensibile e i moduli futuri (`email_inbound`, `telegram_bot`, `mqtt`) devono avere una casa. Non creare altre cartelle.
- **Pattern:** registro `INGESTION_MODULES: dict[str, IngestionModule]` risolto tramite `receivers.ingestion_module`, come da contratto della specifica sezione 6.1. Il core non conosce il canale.
- **Change:**
  - `registry.py` definisce il `Protocol` `IngestionModule` e il dizionario, popolato all'import di `http_raw`.
  - `http_raw.py` implementa il modulo v1: accetta `text/plain` o `Content-Type` assente; qualunque altro tipo -> `415`. Restituisce un `IngestionResult` con `content`, `severity` esplicita se presente, `metadata` vuoto.
  - `api/ingest.py` implementa `POST /ingest/{slug}` **senza prefisso `/api/v1`**, con questa sequenza esatta e in quest'ordine:

    | # | Passo | Esito negativo |
    |---|-------|----------------|
    | 1 | `started_at = time.perf_counter()` | — |
    | 2 | Estrazione dell'IP sorgente: `X-Forwarded-For` **solo** se l'IP del peer e in `settings.trusted_proxies`, altrimenti l'IP del peer | — |
    | 3 | `check_ip_limit(ip)` | `429` con `Retry-After` |
    | 4 | `resolve_slug(slug)` | `respond_not_found(started_at)` |
    | 5 | `check_slug_limit(receiver.id, receiver.rate_limit_per_min)` | `429` con `Retry-After` |
    | 6 | Risoluzione del modulo dal registro | `500` se il nome non e nel registro |
    | 7 | Verifica del `Content-Type` da parte del modulo | `415` |
    | 8 | Se `X-Request-Id` presente: `reserve(...)` | valore `pending` -> `409`; valore con esito -> `200` con quel corpo e header `Idempotent-Replay: true` |
    | 9 | `read_body(request, receiver.max_body_bytes)` | `413` |
    | 10 | `resolve_severity(...)` | mai fallisce (invariante I-7) |
    | 11 | `notification_id = uuid4()`; se `raw_size > INLINE_MAX_BYTES` allora `put_payload(...)` **prima** dell'INSERT | `503` |
    | 12 | `tenant_session(receiver.tenant_id)`: INSERT della notification | — |
    | 13 | `# OUTBOX: la fase 6 inserisce qui la creazione delle Delivery, dentro questa stessa transazione` | — |
    | 14 | Commit, `store_result(...)` se c'era `X-Request-Id`, incremento delle metriche | — |
    | 15 | `201` con `{"id", "severity", "severity_source", "forwarded_to": 0}` | — |

    Il commento del passo 13 e un **commento sentinella obbligatorio**, da scrivere testualmente: la fase 6 sotto-fase 6.4 lo cerca per sapere dove inserire il proprio codice (decisione D12 dell'overview). `forwarded_to` vale `0` in questa fase ed e corretto cosi.
  - Quando `resolve_slug` restituisce `None` **e lo slug esisteva ma il receiver era disabilitato**, non e possibile incrementare il contatore dei rifiuti senza distinguere il caso. La soluzione: `resolve_slug` incrementa internamente `bump_rejected_counter(receiver.id)` prima di restituire `None`, cosi il chiamante resta cieco e il contatore si popola comunque. Il conteggio viene esposto dal dettaglio del receiver in fase 7.
  - Nel `PATCH` del receiver di fase 4 e nel dettaglio, aggiungi il campo `rejected_last_24h` letto con `read_rejected_counter`.
- **Test strategy:** e2e completi contro lo stack di test. Il payload da 2MB si genera nel test, non si versiona un file binario.
- **Unit tests:** `backend/tests/unit/test_ingestion_registry.py::test_modulo_http_raw_registrato` — `INGESTION_MODULES["http_raw"]` esiste e ha attributo `name == "http_raw"`.
- **e2e tests:** in `backend/tests/e2e/test_ingest.py`:
  `T-ING13` `test_ingest_semplice` — `POST /ingest/{slug}` con corpo di testo restituisce `201`, la notification esiste con `content` inline, `storage_backend='inline'`, `severity_source='receiver_default'`.
  `T-ING14` `test_severity_da_regola` — con la regola `FALL(ITO|IMENT)`, il corpo `Backup FALLITO` produce `severity=error` e `severity_source=rule`.
  `T-ING15` `test_severity_esplicita_da_header` — `X-Severity: critical` produce `severity_source=explicit`.
  `T-ING16` `test_severity_non_valida_non_fa_fallire` — `X-Severity: banana` produce comunque `201`. Percorso negativo dell'invariante I-7.
  `T-ING17` `test_corpo_oltre_il_limite` — con `max_body_bytes=1024` e corpo di 2048 byte, risposta `413` e nessuna riga creata.
  `T-ING18` `test_payload_grande_va_su_object_store` — corpo di 2MB: `201`, `storage_backend='object'`, `content is None`, `storage_key` valorizzata, e l'oggetto esiste davvero su MinIO.
  `T-ING19` `test_preview_sempre_valorizzata` — anche per il payload da 2MB, `content_preview` e lungo 4096 caratteri e coincide con l'inizio del corpo.
  `T-ING20` `test_replay_idempotente` — due `POST` con lo stesso `X-Request-Id`: il primo `201`, il secondo `200` con header `Idempotent-Replay: true`, stesso `id` nel corpo, e in tabella **una sola** notification. Percorso negativo: fallisce se la deduplica viene rimossa.
  `T-ING21` `test_request_id_diverso_crea_due_notifiche` — con id diversi si creano due righe. Impedisce una deduplica troppo aggressiva.
  `T-ING22` `test_content_type_non_supportato` — `Content-Type: application/json` restituisce `415`.
  `T-ING23` `test_limite_per_slug` — con `rate_limit_per_min=2`, la terza richiesta nello stesso minuto restituisce `429`.
  `T-ING24` `test_byte_binari_accettati` — corpo `b"\xff\xfe\x00abc"` produce `201`, `content_normalized=True` e `content_size == 6`. Percorso negativo dell'invariante I-7.
  Piu i test `T-ING4`, `T-ING5`, `T-ING6` della sotto-fase 5.2, che ora possono girare per intero.
- **Done:** tutti i `T-ING*` verdi.

---

## Files touched (this phase)

- `backend/app/services/ratelimit.py` — modificato — limiti di ingestion e contatore rifiuti
- `backend/app/services/ingest_lookup.py` — creato — risoluzione slug e 404 uniforme
- `backend/app/services/body_reader.py` — creato — streaming, limite, normalizzazione
- `backend/app/services/severity.py` — modificato — catena completa
- `backend/app/services/storage.py` — modificato — chiave, put, get, delete
- `backend/app/services/idempotency.py` — creato — finestra di deduplica
- `backend/app/ingestion/__init__.py`, `registry.py`, `http_raw.py` — creati — contratto e modulo v1
- `backend/app/api/ingest.py` — creato — endpoint pubblico
- `backend/app/api/v1/receivers.py` — modificato — campo `rejected_last_24h`
- `backend/app/main.py` — modificato — registrazione del router di ingestion
- `backend/alembic/versions/0004_grant_ingest_tenant_status.py` — creato — GRANT su `tenants.status`
- `backend/tests/unit/test_body_reader.py`, `test_severity_chain.py`, `test_storage_key.py`, `test_ingestion_registry.py` — creati
- `backend/tests/integration/test_ratelimit_ingest.py`, `test_storage.py`, `test_idempotency.py` — creati
- `backend/tests/e2e/test_ingest.py`, `test_ingest_404.py` — creati
- `backend/tests/integration/test_rls.py` — modificato — `T-RLS7` adeguato alla nuova GRANT

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** `T-MGMT1` .. `T-MGMT17`, `T-AUTH1` .. `T-AUTH22`, `T-RLS1` .. `T-RLS9` restano verdi.

## Phase done criterion

`make gates` verde con `T-ING1` .. `T-ING24`. Verifica manuale finale: con lo stack avviato e un receiver creato,
`curl --data "Backup FALLITO" http://localhost:8000/ingest/<slug>` restituisce `201` con `severity: "error"`, e
`curl http://localhost:8000/ingest/slug-inventato` restituisce un `404` il cui corpo e identico byte per byte a quello ottenuto disabilitando il receiver.
Il commento sentinella `# OUTBOX:` esiste in `backend/app/api/ingest.py` ed e l'unico punto in cui la fase 6 dovra intervenire.
