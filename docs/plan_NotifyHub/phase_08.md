# Fase 7 — API di consultazione

> **Intent:** rendere le notifiche leggibili, filtrabili, paginabili e scaricabili, con la garanzia che una lista non carichi mai un payload da 20MB.
> **Shippable alone?** si — al termine la API di lettura e completa e il frontend della fase 9 ha tutto cio che gli serve.
> **Preconditions:** fase 6 DONE.

Fonti autoritative: `notifyhub-spec.md` sezione 9.5 (superficie e filtri), sezione 6.5 (flusso di lettura), sezione 4.2 (indici disponibili).

---

## Sub-phases

### 7.1 Lista delle notifiche con paginazione a cursore

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/schemas/notification.py` (nuovo), `backend/app/api/v1/notifications.py` (nuovo), `backend/app/main.py` (modificato).
- **Pattern:** paginazione **keyset**, non `OFFSET`. Con milioni di righe l'offset degrada e produce risultati incoerenti quando arrivano notifiche nuove durante lo scorrimento.
- **Change:**
  - `GET /api/v1/notifications` — `require_viewer`. Parametri: `group_id`, `receiver_id`, `status`, `severity_min`, `q`, `from`, `to`, `limit` (default 50, massimo 200), `cursor`.
  - **Ordinamento fisso**: `received_at DESC, id DESC`. Corrisponde all'indice `ix_notifications_tenant_id_received_at_id` creato in fase 1 sotto-fase 1.7. Non introdurre ordinamenti alternativi.
  - **Cursore**: stringa base64 url-safe di `"{received_at_iso}|{id}"`. La clausola di continuazione e
    ```sql
    (received_at, id) < (:cursor_ts, :cursor_id)
    ```
    che usa il confronto di tuple ed e servita dall'indice. Un cursore malformato -> `422`, non `500`.
  - **Filtri**:
    - `severity_min` confronta l'enum nativo: `severity >= :sev`. Nessuna funzione di mappatura.
    - `group_id` richiede una join su `receivers`, servita da `ix_receivers_tenant_id_group_id`.
    - `q` usa `to_tsvector('simple', content_preview) @@ plainto_tsquery('simple', :q)`, servito dall'indice GIN. **Cerca solo nei primi 4096 caratteri**: la risposta deve includere il campo `search_scope: "preview"` cosi il frontend puo dirlo all'utente.
    - `from` e `to` filtrano `received_at`.
  - **La risposta non contiene mai `content`.** Ogni elemento espone: `id`, `receiver_id`, `receiver_name`, `group_id`, `severity`, `severity_source`, `status`, `received_at`, `content_size`, `content_normalized`, `storage_backend`, e `content_preview` **troncato a 500 caratteri** lato server.
  - Corpo della risposta: `{"items": [...], "next_cursor": "..." | null, "search_scope": "preview" | null}`.
- **Test strategy:** i test di paginazione creano 25 notifiche con `received_at` distinti e scorrono a pagine da 10, verificando che l'unione delle pagine sia esattamente l'insieme di partenza, senza duplicati ne buchi.
- **Unit tests:** in `backend/tests/unit/test_cursor.py`:
  `test_cursore_roundtrip` — codifica e decodifica restituiscono i valori originali.
  `test_cursore_malformato_solleva_422` — una stringa non base64 e una base64 senza separatore producono entrambe `Problem` 422. Percorso negativo.
- **e2e tests:** in `backend/tests/e2e/test_notifications_list.py`:
  `T-CONS1` `test_paginazione_completa_senza_duplicati` — 25 notifiche, tre pagine da 10, l'insieme degli id raccolti coincide con quello atteso e ha cardinalita 25.
  `T-CONS2` `test_lista_non_contiene_content` — la risposta non ha la chiave `content` in nessun elemento, e `content_preview` e lungo al piu 500 caratteri anche per una notifica da 2MB. Percorso negativo: fallisce se qualcuno restituisce il corpo intero.
  `T-CONS3` `test_filtro_severity_min` — con notifiche `info`, `warning`, `error`, il filtro `severity_min=warning` ne restituisce due.
  `T-CONS4` `test_filtro_gruppo` — due gruppi, il filtro restituisce solo le notifiche del gruppo richiesto.
  `T-CONS5` `test_ricerca_testuale` — `q=disco` trova la notifica che contiene quella parola e non le altre.
  `T-CONS6` `test_ricerca_non_entra_oltre_la_preview` — una notifica il cui testo contiene la parola cercata solo al carattere 8000 **non** viene trovata, e `search_scope` vale `preview`. Percorso negativo che documenta il limite dichiarato nella specifica sezione 9.5.
  `T-CONS7` `test_isolamento_fra_tenant` — un token del tenant B non vede alcuna notifica del tenant A.
  `T-CONS8` `test_cursore_stabile_con_inserimenti` — dopo aver letto la prima pagina, l'inserimento di una notifica nuova non provoca duplicati nella seconda pagina.
- **Done:** gli otto test passano.

### 7.2 Dettaglio e scaricamento del contenuto

- **Model:** Sonnet
- **Files:** `backend/app/api/v1/notifications.py` (modificato).
- **Insertion point:** in coda al router creato in 7.1.
- **Change:**
  - `GET /api/v1/notifications/{id}` — `require_viewer`. Se `storage_backend == 'inline'` la risposta include `content` per intero. Se e `'object'`, `content` vale `null` e la risposta include `content_url = "/api/v1/notifications/{id}/content"`. La risposta include sempre `content_size`, `content_normalized`, `severity_source` e il nome della regola che ha deciso la severity, se `severity_source == 'rule'`.
  - `GET /api/v1/notifications/{id}/content` — `require_viewer`. Restituisce il corpo completo in streaming:
    - `inline`: `Response` con il testo della colonna;
    - `object`: `StreamingResponse` alimentata da `get_payload_stream` della fase 5 sotto-fase 5.5, con `Content-Type: text/plain; charset=utf-8` e `Content-Length` da `content_size`.
    L'autorizzazione avviene **prima** di aprire lo stream: la riga si carica dentro `tenant_session`, quindi la RLS ha gia filtrato. **Nessuna presigned URL viene mai generata** (specifica sezione 6.5): il download passa sempre dall'API.
  - Se `storage_backend == 'object'` ma l'oggetto non esiste su MinIO, rispondi `503` con `type=/problems/storage-unavailable`, non `404`: la notifica esiste, e lo storage a essere in difficolta.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_notifications_detail.py`:
  `T-CONS9` `test_dettaglio_inline` — la risposta contiene `content` uguale al corpo inviato e `content_url` assente.
  `T-CONS10` `test_dettaglio_offloaded` — per una notifica da 2MB, `content is None` e `content_url` valorizzato.
  `T-CONS11` `test_download_restituisce_i_byte_originali` — il download della notifica da 2MB restituisce esattamente i byte inviati, confrontati per hash SHA-256. E il test che dimostra che l'offload non corrompe nulla.
  `T-CONS12` `test_download_di_altro_tenant_e_404` — un token del tenant B che chiede il contenuto di una notifica del tenant A riceve `404`, non `403`: la RLS l'ha resa invisibile. Percorso negativo.
  `T-CONS13` `test_oggetto_mancante_da_503` — cancellato l'oggetto direttamente da MinIO, il download restituisce `503`.
- **Done:** i cinque test passano.

### 7.3 Stato di lettura e cancellazione

- **Model:** Sonnet
- **Files:** `backend/app/api/v1/notifications.py` (modificato).
- **Change:**
  - `PATCH /api/v1/notifications/{id}` — `require_viewer`. Corpo `{"status": "read" | "unread"}`. Segnare come letta e consentito anche al ruolo `viewer`, come da matrice ruoli.
  - `POST /api/v1/notifications/bulk-read` — `require_viewer`. Corpo con gli stessi filtri della lista (`group_id`, `receiver_id`, `severity_min`, `from`, `to`). Esegue un `UPDATE` massivo e restituisce `{"updated": n}`. **Non accetta un elenco di id illimitato**: opera per filtro, cosi la query resta indicizzata.
  - `DELETE /api/v1/notifications/{id}` — **`require_member`**: il `viewer` non cancella. La cancellazione della riga fa scattare il trigger di fase 1 che accoda la `storage_key` in `pending_object_deletions` (invariante I-8). L'endpoint **non** cancella l'oggetto direttamente: se lo facesse e la transazione andasse in rollback, il payload sarebbe perso per sempre.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_notifications_write.py`:
  `T-CONS14` `test_segna_letta_e_non_letta` — il campo `status` cambia in entrambe le direzioni.
  `T-CONS15` `test_bulk_read_per_filtro` — con dieci notifiche di cui quattro `error`, `bulk-read` con `severity_min=error` restituisce `updated: 4` e le altre sei restano `unread`. Percorso negativo: fallisce se il filtro viene ignorato.
  `T-CONS16` `test_viewer_non_puo_cancellare` — con token `viewer`, `DELETE` restituisce `403`.
  `T-CONS17` `test_cancellazione_accoda_oggetto` — cancellata una notifica con `storage_backend='object'`, `pending_object_deletions` contiene la sua `storage_key`, e **l'oggetto e ancora su MinIO** perche la cancellazione effettiva spetta al job di fase 8. Percorso negativo dell'invariante I-8.
  `T-CONS18` `test_cancellazione_inline_non_accoda` — nessuna riga accodata.
- **Done:** i cinque test passano.

### 7.4 Riepilogo per la home della dashboard

- **Model:** Haiku
- **Files:** `backend/app/api/v1/stats.py` (nuovo), `backend/app/main.py` (modificato).
- **Pattern:** una sola query con aggregazioni condizionali, non quattro query separate.
- **Change:** `GET /api/v1/stats/summary` — `require_viewer`. Restituisce:
  ```json
  {
    "unread_total": 12,
    "by_severity": {"debug": 0, "info": 40, "warning": 5, "error": 3, "critical": 1},
    "by_group": [{"group_id": "...", "name": "...", "total": 30, "unread": 4}],
    "last_24h_total": 18,
    "deliveries_dead": 2
  }
  ```
  Tutte le chiavi di `by_severity` sono sempre presenti, anche a zero: un frontend che deve gestire chiavi mancanti e un frontend che sbaglia.
- **Unit tests:** nessuno.
- **e2e tests:** `T-CONS19` in `backend/tests/e2e/test_stats.py::test_riepilogo` — con un insieme noto di notifiche, tutti i conteggi corrispondono e `by_severity` ha esattamente cinque chiavi.
  `T-CONS20` `test_riepilogo_isolato_per_tenant` — i conteggi del tenant B non includono nulla del tenant A. Percorso negativo.
- **Done:** i due test passano; `make gates` verde.

---

## Files touched (this phase)

- `backend/app/schemas/notification.py` — creato — schemi di lista, dettaglio, filtri
- `backend/app/api/v1/notifications.py` — creato — lista, dettaglio, contenuto, stato, cancellazione
- `backend/app/api/v1/stats.py` — creato — riepilogo
- `backend/app/main.py` — modificato — registrazione dei due router
- `backend/tests/unit/test_cursor.py` — creato
- `backend/tests/e2e/test_notifications_list.py`, `test_notifications_detail.py`, `test_notifications_write.py`, `test_stats.py` — creati

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** `T-OUT1` .. `T-OUT26` e `T-ING1` .. `T-ING24` restano verdi.

## Phase done criterion

`make gates` verde con `T-CONS1` .. `T-CONS20`. `T-CONS11` dimostra che una notifica da 2MB si riscarica identica; `T-CONS2` che la lista non trasporta mai il corpo; `T-CONS17` che la cancellazione accoda l'oggetto invece di rimuoverlo subito.
