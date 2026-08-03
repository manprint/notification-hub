# Fase 6 — Outbound: canali, outbox, worker, formattazione, ritenti

> **Intent:** portare le notifiche fuori da NotifyHub verso Slack e Google Chat con il pattern outbox, senza che l'ingestion attenda mai la rete.
> **Shippable alone?** si — al termine una notifica sopra soglia arriva davvero su un webhook.
> **Preconditions:** fase 5 DONE. Il commento sentinella `# OUTBOX:` esiste in `backend/app/api/ingest.py`.

Fonti autoritative: `notifyhub-spec.md` sezione 4.3 (tabelle e macchina a stati), sezione 8.1 (risoluzione destinazioni), 8.2 (outbox e worker), 8.3 (accodamento dopo il commit), 8.4 (sessione sincrona), 8.5 (formattazione), sezione 9.4 (API).

Invarianti in gioco: **I-4** (il worker non legge mai `content` ne MinIO), **I-5** (nessun task accodato dentro una transazione), **I-6** (i webhook non escono mai in chiaro).

---

## Sub-phases

### 6.1 Canali di consegna

- **Model:** Sonnet
- **Files:** `backend/app/schemas/channel.py` (nuovo), `backend/app/api/v1/channels.py` (nuovo), `backend/app/main.py` (modificato).
- **Pattern:** il webhook entra in chiaro e viene subito cifrato con `encrypt_secret` della fase 2 sotto-fase 2.3; esce solo come hint prodotto da `mask_webhook`.
- **Change:**
  - `POST /api/v1/channels` — `require_member`. Corpo: `name`, `type` (`slack` o `google_chat`), `webhook_url`. **Validazione dell'URL: lo schema deve essere `http` o `https` e l'host deve comparire in `settings.webhook_host_allowlist`** (fase 2 sotto-fase 2.1), altrimenti `422`. Il default della lista contiene i soli due endpoint ufficiali, entrambi HTTPS; l'elenco e configurabile perche lo smoke test della fase 10 punta a un ricevitore interno. Il controllo sull'host, non sullo schema, e cio che impedisce di usare NotifyHub per emettere richieste verso host arbitrari. Persiste `encrypt_secret(webhook_url)` nella colonna `bytea`.
  - `GET /api/v1/channels` — `require_member`. **Nessuna risposta contiene mai il webhook in chiaro**: solo `webhook_hint` prodotto da `mask_webhook`.
  - `PATCH|DELETE /api/v1/channels/{id}` — `require_member`. Il PATCH accetta un nuovo `webhook_url`, che viene ricifrato; se il campo e assente, il valore esistente resta invariato.
  - La risposta di dettaglio include `last_success_at`, `last_error_at`, `last_error`.
- **Unit tests:** nessuno oltre a quelli di `crypto` gia esistenti.
- **e2e tests:** in `backend/tests/e2e/test_channels.py`:
  `T-OUT1` `test_crea_canale_e_maschera` — la risposta di creazione contiene `webhook_hint` e **non** contiene la stringa del webhook originale in nessun campo. Percorso negativo dell'invariante I-6.
  `T-OUT2` `test_webhook_cifrato_in_tabella` — una query diretta su `delivery_channels.webhook_url` restituisce byte che non contengono la URL in chiaro.
  `T-OUT3` `test_host_fuori_allowlist_rifiutato` — `https://evil.example.com/hook` restituisce `422` e nessun canale viene creato. Percorso negativo: fallisce se il controllo sull'host viene rimosso.
  `T-OUT4` `test_viewer_non_vede_canali` — con token `viewer`, `GET /api/v1/channels` restituisce `403`, come da matrice ruoli.
- **Done:** i quattro test passano.

### 6.2 Binding di gruppo e override di receiver

- **Model:** Sonnet
- **Files:** `backend/app/schemas/binding.py` (nuovo), `backend/app/api/v1/bindings.py` (nuovo), `backend/app/main.py` (modificato).
- **Pattern:** sotto-risorse indirizzabili per `channel_id`, come stabilito nella specifica sezione 9.4. Un `PUT` o `DELETE` su una collezione senza identificativo e un errore di disegno: non farlo.
- **Change:**
  - `GET|POST /api/v1/groups/{id}/channels` — elenco e creazione del binding, con `min_severity` (default `error`) e `enabled`.
  - `PUT|DELETE /api/v1/groups/{id}/channels/{channel_id}` — modifica e rimozione.
  - `GET|POST /api/v1/receivers/{id}/channels` — elenco e creazione dell'override, con `mode` (`override` o `mute`) e `min_severity` obbligatoria se `mode == override`, altrimenti deve essere assente -> `422`.
  - `PUT|DELETE /api/v1/receivers/{id}/channels/{channel_id}`.
  - Tutti `require_member`.
  - Il vincolo di unicita su `(group_id, channel_id)` e `(receiver_id, channel_id)` produce `409` sulla creazione duplicata.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_bindings.py`:
  `T-OUT5` `test_binding_creato_e_modificato` — creazione `201`, `PUT` cambia `min_severity`, l'elenco riflette la modifica.
  `T-OUT6` `test_override_senza_min_severity_rifiutato` — `mode=override` senza `min_severity` restituisce `422`. Percorso negativo.
  `T-OUT7` `test_mute_con_min_severity_rifiutato` — `mode=mute` con `min_severity` valorizzata restituisce `422`.
  `T-OUT8` `test_binding_duplicato_rifiutato` — la seconda creazione sullo stesso canale restituisce `409`.
- **Done:** i quattro test passano.

### 6.3 Risoluzione delle destinazioni

- **Model:** Sonnet
- **Files:** `backend/app/services/outbound_resolver.py` (nuovo).
- **Pattern:** funzione pura sul risultato di **una sola query**; nessun accesso al database dentro il ciclo.
- **Change:**
  ```python
  async def resolve_targets(session, receiver_id, group_id, severity) -> list[UUID]
  ```
  Esegue una query che carica in un colpo solo i binding abilitati del gruppo, con LEFT JOIN sugli override del receiver e sullo stato `enabled` del canale. Poi applica l'algoritmo della specifica sezione 8.1, testualmente:
  ```
  per ogni binding abilitato del gruppo:
      se override.mode == 'mute'      -> scarta
      se override.mode == 'override'  -> soglia = override.min_severity
      altrimenti                      -> soglia = binding.min_severity
      se severity >= soglia AND channel.enabled -> il canale e una destinazione
  ```
  Il confronto `severity >= soglia` si fa **in SQL sull'enum nativo** oppure in Python usando `SEVERITY_ORDER` di fase 1 sotto-fase 1.2. Non introdurre alcuna funzione SQL di mappatura a intero.
  Restituisce la lista degli `channel_id` destinatari, eventualmente vuota.
- **Test strategy:** unitari sul database di test, costruendo le combinazioni; questa e la funzione con piu casi limite dell'intera fase e va coperta a matrice.
- **Unit tests:** in `backend/tests/integration/test_resolver.py` (marker `integration`), una tabella di casi:

  | Caso | Binding | Override | Severity | Atteso |
  |------|---------|----------|----------|--------|
  | `test_sopra_soglia_inoltra` | error | assente | critical | canale presente |
  | `test_sotto_soglia_non_inoltra` | error | assente | warning | lista vuota |
  | `test_uguale_alla_soglia_inoltra` | error | assente | error | canale presente |
  | `test_mute_scarta` | error | mute | critical | lista vuota |
  | `test_override_abbassa_soglia` | error | override info | info | canale presente |
  | `test_override_alza_soglia` | info | override critical | error | lista vuota |
  | `test_binding_disabilitato_scarta` | error disabled | assente | critical | lista vuota |
  | `test_canale_disabilitato_scarta` | error, canale disabled | assente | critical | lista vuota |

  I casi `test_mute_scarta`, `test_sotto_soglia_non_inoltra` e `test_override_alza_soglia` sono i percorsi negativi: falliscono se la logica di scarto viene rimossa.
- **e2e tests:** coperti da 6.4.
- **Done:** gli otto casi passano.

### 6.4 Creazione delle Delivery nella transazione di ingestion

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/api/ingest.py` (modificato).
- **Insertion point:** **esattamente** al commento sentinella lasciato dalla fase 5:
  ```python
  # OUTBOX: la fase 6 inserisce qui la creazione delle Delivery, dentro questa stessa transazione
  ```
  Il codice va inserito al posto del commento, **dentro la stessa `tenant_session`** che ha appena inserito la notification. Se il commento non esiste, **fermati e chiedi**: significa che la fase 5 non e stata completata come previsto.
- **Change:**
  - chiama `resolve_targets(...)` con la sessione corrente;
  - per ogni canale destinatario inserisce una riga `deliveries` con `status='pending'`, `attempts=0`, `next_attempt_at=now()`;
  - accumula le coppie `(delivery_id, tenant_id)` in una lista locale, che la sotto-fase 6.5 usera per l'accodamento **dopo** il commit;
  - aggiorna il campo `forwarded_to` della risposta con il numero di delivery create, sostituendo lo `0` fisso della fase 5.
  > **Attenzione, cambio di comportamento.** `T-ING13` e gli altri test di fase 5 asserivano `forwarded_to == 0`. Ora quel valore riflette le destinazioni reali. Aggiorna quelle asserzioni: nei test di fase 5 non esiste alcun binding, quindi il valore resta `0` e i test restano verdi senza modifiche. Se un test di fase 5 fallisce dopo questa modifica, la causa e un binding creato per errore da una fixture condivisa: correggi la fixture, non l'asserzione.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_outbox.py`:
  `T-OUT9` `test_delivery_creata_nella_stessa_transazione` — con un binding a `error` e una notifica `error`, dopo la risposta `201` esiste una riga `deliveries` in stato `pending` e `forwarded_to == 1`.
  `T-OUT10` `test_nessuna_delivery_sotto_soglia` — notifica `info` con binding a `error`: nessuna riga `deliveries`, `forwarded_to == 0`. Percorso negativo.
  `T-OUT11` `test_rollback_non_lascia_delivery` — forzando un errore dopo l'inserimento della delivery e prima del commit (con un monkeypatch che solleva), non restano ne la notification ne la delivery: la transazione e davvero unica.
- **Done:** i tre test passano.

### 6.5 Accodamento dopo il commit

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/tasks/enqueue.py` (nuovo), `backend/app/api/ingest.py` (modificato).
- **Pattern:** astrazione iniettabile (decisione D7 dell'overview). L'accodamento reale usa Celery; nei test si sostituisce con un raccoglitore in memoria. E cosi che l'ordine commit-poi-enqueue diventa verificabile senza broker.
- **Change:**
  - `app/tasks/enqueue.py` espone:
    ```python
    Enqueuer = Callable[[UUID, UUID], None]
    def celery_enqueuer(delivery_id: UUID, tenant_id: UUID) -> None
    _current: Enqueuer = celery_enqueuer
    def set_enqueuer(fn: Enqueuer) -> None      # solo per i test
    def enqueue_delivery(delivery_id: UUID, tenant_id: UUID) -> None
    ```
  - in `api/ingest.py`, l'accodamento si registra con l'evento di sessione, **non** con una chiamata diretta:
    ```python
    @event.listens_for(session.sync_session, "after_commit")
    def _enqueue(_: object) -> None:
        for delivery_id, tenant_id in pending_dispatch:
            enqueue_delivery(delivery_id, tenant_id)
    ```
    Chiamare `enqueue_delivery` dentro il blocco `async with tenant_session(...)` e l'errore che questa sotto-fase esiste per impedire: il worker e piu veloce del commit e cerca una riga che non vede ancora (invariante I-5).
  - se il processo muore fra commit e accodamento il task si perde e la riga resta `pending`: la ripesca `reconcile_deliveries` in fase 8. L'hook e l'ottimizzazione di latenza, il riconciliatore e la garanzia.
- **Test strategy:** un enqueuer finto che, al momento della chiamata, apre una **connessione separata** e verifica che la riga sia gia visibile. E l'unico modo di dimostrare l'ordine.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_outbox.py`:
  `T-OUT12` `test_accodamento_dopo_il_commit` — l'enqueuer finto, quando invocato, esegue `SELECT` su `deliveries` da una connessione nuova e trova la riga. Asserisce inoltre che l'enqueuer sia stato chiamato esattamente una volta. **Verifica di autenticita obbligatoria:** sposta temporaneamente la chiamata dentro la transazione e verifica che questo test diventi rosso; poi ripristina.
  `T-OUT13` `test_nessun_accodamento_se_rollback` — con un errore prima del commit, l'enqueuer non viene mai invocato. Percorso negativo.
- **Done:** i due test passano e la verifica di autenticita e stata eseguita.

### 6.6 Applicazione Celery e sessione sincrona

- **Model:** Sonnet
- **Files:** `backend/app/tasks/celery_app.py` (nuovo), `backend/app/tasks/delivery.py` (nuovo).
- **Pattern:** i worker usano `tenant_session_sync` creata in fase 1 sotto-fase 1.9. **Nessun `asyncio.run` dentro un task** (specifica sezione 8.4): aprire un event loop per task e la causa piu comune di connessioni appese.
- **Change:**
  - `celery_app.py` costruisce `Celery("notifyhub", broker=settings.celery_broker_url)` con `task_acks_late=True`, `worker_prefetch_multiplier=1`, coda predefinita `delivery`, serializzatore `json`.
  - `delivery.py` definisce il task `dispatch_delivery(delivery_id: str, tenant_id: str)`, per ora con il solo scheletro: apre `tenant_session_sync`, carica la delivery, e delega a `send_delivery(...)` della sotto-fase 6.8, che in questo momento non esiste ancora. Crea la funzione con un corpo che solleva `NotImplementedError` e completala in 6.8.
  - `celery_enqueuer` di 6.5 chiama `dispatch_delivery.delay(...)`.
  - Le chiamate HTTP verso i webhook usano `httpx` **sincrono** dentro il task, non `aiohttp` e non `httpx.AsyncClient`.
- **Unit tests:** `backend/tests/unit/test_celery_config.py::test_configurazione_worker` — asserisce `task_acks_late is True` e `worker_prefetch_multiplier == 1`. Con `acks_late` disattivato un worker ucciso perde il messaggio senza che nessuno se ne accorga.
- **e2e tests:** nessuno (il comportamento arriva in 6.8).
- **Done:** `make types` verde; il modulo importabile senza broker attivo.

### 6.7 Formattazione dei messaggi

- **Model:** Sonnet
- **Files:** `backend/app/outbound/formatters/slack.py` (nuovo), `backend/app/outbound/formatters/google_chat.py` (nuovo), `backend/app/outbound/formatters/__init__.py` (modificato).
- **Pattern:** funzioni pure. Ingresso: un oggetto `NotificationSummary` con `severity`, `receiver_name`, `content_preview`, `content_size`, `dashboard_url`, `received_at`. **Non riceve `content` e non riceve `storage_key`**: e cosi che l'invariante I-4 diventa impossibile da violare per costruzione.
- **Change:**
  - `format_slack(summary) -> dict` — Block Kit: un blocco `header` con severity e nome del receiver, un blocco `section` con i primi **2800** caratteri di `content_preview`, un blocco `context` con il link alla dashboard. Colore per severity: `critical` e `error` rosso, `warning` giallo, `info` e `debug` grigio.
  - `format_google_chat(summary) -> dict` — `cardV2` con titolo, testo troncato a **3800** caratteri, bottone "Apri in NotifyHub".
  - Se il testo viene troncato, entrambi i formatter accodano la dicitura esatta `… [troncato, N KB totali]` dove `N` e `content_size` diviso 1024 arrotondato. Se non c'e troncamento, la dicitura non compare.
- **Unit tests:** in `backend/tests/unit/test_formatters.py`:
  `test_slack_tronca_a_2800` — con preview di 4096 caratteri, il testo del blocco `section` e lungo al piu 2800 caratteri piu la dicitura, e la dicitura c'e.
  `test_nessuna_dicitura_se_non_troncato` — con preview di 100 caratteri, la dicitura non compare. Percorso negativo: impedisce di segnalare sempre il troncamento.
  `test_kb_totali_dalla_dimensione_reale` — con `content_size = 2 * 1024 * 1024`, la dicitura riporta `2048 KB`, cioe la dimensione dell'originale e non quella della preview.
  `test_colore_per_severity` — quattro asserzioni sulla mappa dei colori.
  `test_formatter_non_accetta_content` — asserisce che `NotificationSummary` **non** abbia i campi `content` e `storage_key`. E il test che protegge l'invariante I-4.
- **e2e tests:** nessuno.
- **Done:** i cinque test passano.

### 6.8 Invio, macchina a stati, ritenti

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/outbound/sender.py` (nuovo), `backend/app/tasks/delivery.py` (modificato).
- **Pattern:** la funzione riceve una sessione gia aperta e la delivery gia caricata; decide lo stato successivo e lo scrive. Nessuna decisione di stato altrove.
- **Change:** `send_delivery(session, delivery, channel, summary) -> None` esegue:
  1. transizione a `sending` con `locked_at = now()`, commit intermedio, cosi il riconciliatore vede il lock;
  2. decifra il webhook con `decrypt_secret`, formatta con il formatter del tipo di canale, esegue il `POST` con `httpx` sincrono, timeout 10 secondi;
  3. applica la macchina a stati della specifica sezione 4.3, tabella completa:

     | Esito | Stato risultante | Effetti |
     |-------|------------------|---------|
     | `2xx` | `sent` | `sent_at = now()`, `channel.last_success_at = now()` |
     | `429` | `failed` | `next_attempt_at` da header `Retry-After` se presente, altrimenti dal backoff |
     | `5xx` o timeout o errore di rete | `failed` | `next_attempt_at` dal backoff, `attempts += 1` |
     | `4xx` diverso da `429` | `dead` | `channel.last_error` e `last_error_at` aggiornati |
     | `attempts` raggiunge 5 | `dead` | nessun ulteriore ritento |

  4. il backoff e la sequenza fissa `[30, 120, 600, 3600, 21600]` secondi indicizzata da `attempts`, piu un jitter casuale fra 0 e il 10 per cento del valore;
  5. `locked_at` torna a `NULL` in tutti gli stati terminali o di attesa.

  `last_error` contiene il codice di stato e i primi 200 caratteri del corpo di risposta, **mai** la URL del webhook (invariante I-6).
  Il task `dispatch_delivery` di 6.6 ora carica delivery, canale e il `NotificationSummary` (leggendo solo `content_preview` e `content_size`) e chiama `send_delivery`.
- **Test strategy:** `respx` intercetta le chiamate `httpx` e simula ogni esito. Nessuna rete reale.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_sender.py` (marker `integration`), un test per riga della tabella:
  `T-OUT14` `test_2xx_diventa_sent`, `T-OUT15` `test_5xx_diventa_failed_con_backoff` (asserisce `next_attempt_at` a circa 30 secondi e `attempts == 1`), `T-OUT16` `test_429_rispetta_retry_after` (header `Retry-After: 120` produce `next_attempt_at` a circa 120 secondi), `T-OUT17` `test_4xx_diventa_dead_subito` (`attempts` resta 1 e lo stato e `dead`), `T-OUT18` `test_quinto_tentativo_diventa_dead`, `T-OUT19` `test_timeout_diventa_failed`.
  `T-OUT20` `test_worker_non_legge_content` — la notification ha `storage_backend='object'` e `content is None`; l'invio riesce comunque e nessuna chiamata a `get_payload_stream` viene effettuata (verificato con un monkeypatch che solleva se invocato). E il test dell'invariante I-4. Percorso negativo: fallisce se qualcuno fa leggere il payload al worker.
  `T-OUT21` `test_last_error_non_contiene_il_webhook` — dopo un `4xx`, `channel.last_error` non contiene la URL. Percorso negativo dell'invariante I-6.
- **Done:** gli otto test passano.

### 6.9 API di diagnostica delle consegne

- **Model:** Sonnet
- **Files:** `backend/app/schemas/delivery.py` (nuovo), `backend/app/api/v1/deliveries.py` (nuovo), `backend/app/main.py` (modificato).
- **Change:**
  - `GET /api/v1/deliveries?status=&channel_id=&limit=&cursor=` — **`require_viewer`**, come da matrice ruoli: la diagnostica e in lettura per tutti. Ordinamento per `created_at` decrescente, paginazione a cursore come le notifiche.
  - `POST /api/v1/deliveries/{id}/retry` — `require_member`. Ammesso **solo** su delivery in stato `dead`: su qualunque altro stato risponde `409`. Riporta la riga a `pending`, azzera `attempts`, `last_error` e `locked_at`, imposta `next_attempt_at = now()` e accoda con `enqueue_delivery` **dopo il commit**, riusando lo stesso meccanismo di 6.5.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_deliveries.py`:
  `T-OUT22` `test_elenco_filtrato_per_stato` — con delivery in stati diversi, il filtro restituisce solo quelle richieste.
  `T-OUT23` `test_retry_su_dead_riaccoda` — la riga torna `pending` con `attempts == 0` e l'enqueuer finto e stato chiamato una volta.
  `T-OUT24` `test_retry_su_pending_rifiutato` — `409`. Percorso negativo.
  `T-OUT25` `test_viewer_puo_leggere_deliveries` — con token `viewer`, `GET` restituisce `200`; `POST .../retry` restituisce `403`.
- **Done:** i quattro test passano.

### 6.10 Prova del canale

- **Model:** Haiku
- **Files:** `backend/app/api/v1/channels.py` (modificato).
- **Insertion point:** in coda al router creato in 6.1.
- **Pattern:** endpoint sottile che riusa i formatter di 6.7 e il client HTTP, senza creare righe `deliveries`.
- **Change:** `POST /api/v1/channels/{id}/test` — `require_member`. Costruisce un `NotificationSummary` finto con severity `info`, testo `"Messaggio di prova da NotifyHub"` e il link alla dashboard, lo formatta e lo invia. Risposta `200` con `{"ok": true, "response_code": 204}` in caso di successo, `502` con `{"ok": false, "response_code": ..., "error": "..."}` in caso di fallimento. Aggiorna `last_success_at` o `last_error_at` sul canale. **Non crea alcuna riga in `deliveries`**.
- **Unit tests:** nessuno.
- **e2e tests:** `T-OUT26` in `backend/tests/e2e/test_channels.py::test_prova_canale` — con `respx` che risponde `200`, l'endpoint restituisce `ok: true`, `last_success_at` e valorizzato e la tabella `deliveries` e rimasta vuota. Con `respx` che risponde `404`, l'endpoint restituisce `502` e `ok: false`.
- **Done:** il test passa; `make gates` verde.

---

## Files touched (this phase)

- `backend/app/schemas/channel.py`, `binding.py`, `delivery.py` — creati
- `backend/app/api/v1/channels.py`, `bindings.py`, `deliveries.py` — creati
- `backend/app/services/outbound_resolver.py` — creato — algoritmo della sezione 8.1
- `backend/app/tasks/enqueue.py` — creato — astrazione di accodamento iniettabile
- `backend/app/tasks/celery_app.py`, `delivery.py` — creati — worker e task
- `backend/app/outbound/sender.py` — creato — invio e macchina a stati
- `backend/app/outbound/formatters/slack.py`, `google_chat.py`, `__init__.py` — creati
- `backend/app/api/ingest.py` — modificato — creazione delivery al sentinella `# OUTBOX:` e hook `after_commit`
- `backend/app/main.py` — modificato — registrazione dei tre router
- `backend/tests/unit/test_celery_config.py`, `test_formatters.py` — creati
- `backend/tests/integration/test_resolver.py`, `test_sender.py` — creati
- `backend/tests/e2e/test_channels.py`, `test_bindings.py`, `test_outbox.py`, `test_deliveries.py` — creati

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** `T-ING1` .. `T-ING24` restano verdi, in particolare `T-ING13` e `T-ING20`.

## Phase done criterion

`make gates` verde con `T-OUT1` .. `T-OUT26`. Le due verifiche di autenticita sono state eseguite e ripristinate: spostando l'accodamento dentro la transazione `T-OUT12` diventa rosso; facendo leggere il payload al worker `T-OUT20` diventa rosso. Nessun campo di risposta dell'API contiene mai un webhook in chiaro.
