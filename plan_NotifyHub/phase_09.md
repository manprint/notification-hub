# Fase 8 — Manutenzione, quote, osservabilita

> **Intent:** rendere il sistema sostenibile nel tempo: purge, riconciliazione, cancellazione degli oggetti, recupero degli orfani, quote per tenant, metriche complete.
> **Shippable alone?** si — al termine il sistema si mantiene da solo e si osserva.
> **Preconditions:** fase 7 DONE.

Fonti autoritative: `notifyhub-spec.md` sezione 11 (tabella dei job), sezione 6.5 (cancellazione oggetti e orfani), sezione 4.1 (colonne di quota), sezione 8.2 (riconciliazione).

Regola trasversale della fase: **nessun job usa privilegi speciali** (invariante I-1). I job che toccano dati di tenant iterano i tenant e aprono `tenant_session_sync(tenant_id)` per ciascuno; i job che lavorano su `pending_object_deletions` operano su una tabella fuori da RLS.

---

## Sub-phases

### 8.1 Pianificazione di Celery Beat

- **Model:** Haiku
- **Files:** `backend/app/tasks/celery_app.py` (modificato), `backend/app/tasks/maintenance.py` (nuovo, solo gli scheletri).
- **Insertion point:** in `celery_app.py`, dopo la configurazione creata in fase 6 sotto-fase 6.6.
- **Change:** aggiungi `beat_schedule` con esattamente le sette voci della specifica sezione 11, con questi nomi di task e queste pianificazioni:

  | Nome del task | Pianificazione (crontab) |
  |---------------|--------------------------|
  | `purge_notifications` | `minute=0, hour=3` |
  | `purge_deliveries` | `minute=30, hour=3` |
  | `cleanup_tokens` | `minute=0` (ogni ora) |
  | `reconcile_deliveries` | `minute="*/5"` |
  | `drain_object_deletions` | `minute="*/10"` |
  | `purge_orphan_objects` | `minute=0, hour=4` |
  | `recompute_tenant_usage` | `minute=30, hour=4` |

  Imposta `timezone = "UTC"` e `enable_utc = True`: pianificare in ora locale su un self-hosted distribuito produce comportamenti che nessuno riesce a spiegare.
  In `maintenance.py` crea le sette funzioni come task Celery con corpo `raise NotImplementedError`, da completare nelle sotto-fasi seguenti.
- **Unit tests:** `backend/tests/unit/test_beat_schedule.py::test_sette_job_pianificati` — asserisce che `beat_schedule` abbia esattamente sette voci con i nomi della tabella. Fallisce se un job viene dimenticato o rinominato.
- **e2e tests:** nessuno.
- **Done:** il test passa; `celery -A app.tasks.celery_app beat --dry-run` non e disponibile, quindi verifica con `python -c "from app.tasks.celery_app import celery_app; print(len(celery_app.conf.beat_schedule))"` che stampi `7`.

### 8.2 Purge delle notifiche e delle consegne

- **Model:** Sonnet
- **Files:** `backend/app/tasks/maintenance.py` (modificato).
- **Pattern:** cancellazione a lotti con `DELETE ... WHERE id IN (SELECT id ... LIMIT 10000)` in un ciclo, un commit per lotto. Un `DELETE` unico su milioni di righe tiene il lock troppo a lungo.
- **Change:**
  - `purge_notifications()` — per ogni tenant con `retention_days` non nullo: apre `tenant_session_sync(tenant.id)` e cancella a lotti da 10.000 le notifiche con `received_at < now() - retention_days`. Registra nel log il numero di righe rimosse per tenant. Il trigger di fase 1 accoda automaticamente le chiavi degli oggetti: **il job non deve toccare MinIO** (invariante I-8).
  - `purge_deliveries()` — per ogni tenant, cancella le delivery in stato `sent` con `sent_at < now() - 30 giorni`. Le `dead` **non** si toccano mai: restano per la diagnostica finche qualcuno non le archivia a mano (specifica sezione 11).
  - L'elenco dei tenant si ottiene con una query su `tenants`, che e fuori da RLS.
- **Test strategy:** integrazione con date manipolate tramite valori espliciti di `received_at`, non con `freezegun`, cosi si prova la query reale.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_purge.py` (marker `integration`):
  `T-MAINT1` `test_purge_rispetta_retention` — con `retention_days=30`, una notifica di 40 giorni fa sparisce e una di 10 giorni fa resta.
  `T-MAINT2` `test_purge_salta_tenant_senza_retention` — con `retention_days` nullo nessuna notifica viene rimossa, nemmeno quelle vecchissime. Percorso negativo.
  `T-MAINT3` `test_purge_isolato_per_tenant` — la retention del tenant A non tocca il tenant B, che ha impostazioni diverse.
  `T-MAINT4` `test_purge_accoda_gli_oggetti` — le notifiche rimosse con `storage_backend='object'` compaiono in `pending_object_deletions`.
  `T-MAINT5` `test_purge_deliveries_non_tocca_dead` — con una `sent` vecchia e una `dead` vecchia, sparisce solo la prima. Percorso negativo.
- **Done:** i cinque test passano.

### 8.3 Pulizia di token e inviti

- **Model:** Sonnet
- **Files:** `backend/app/tasks/maintenance.py` (modificato).
- **Change:** `cleanup_tokens()` — per ogni tenant: cancella i `refresh_tokens` con `expires_at < now()` oppure `revoked_at` non nullo e piu vecchio di sette giorni; cancella gli `invitations` con `expires_at < now()` e `accepted_at` nullo. Gli inviti gia accettati restano come traccia di audit.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_purge.py`:
  `T-MAINT6` `test_cleanup_token_scaduti` — un token scaduto sparisce, uno valido resta.
  `T-MAINT7` `test_cleanup_conserva_inviti_accettati` — un invito scaduto ma accettato resta in tabella. Percorso negativo: fallisce se la condizione su `accepted_at` viene omessa.
- **Done:** i due test passano.

### 8.4 Riconciliazione delle consegne

- **Model:** Sonnet
- **Files:** `backend/app/tasks/maintenance.py` (modificato).
- **Pattern:** il job non invia nulla: ri-accoda. L'invio resta responsabilita di `dispatch_delivery`.
- **Change:** `reconcile_deliveries()` — per ogni tenant seleziona e ri-accoda:
  1. le delivery in stato `pending` o `failed` con `next_attempt_at <= now()`;
  2. le delivery in stato `sending` con `locked_at < now() - 10 minuti`, che indicano un worker morto a meta: prima di ri-accodare le riporta a `failed` e azzera `locked_at`.
  Limite di 500 righe per ciclo per non saturare la coda. L'accodamento usa `enqueue_delivery` della fase 6 sotto-fase 6.5, sempre **dopo** il commit della transazione che ha aggiornato gli stati (invariante I-5).
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_reconcile.py` (marker `integration`):
  `T-MAINT8` `test_pending_scaduta_riaccodata` — una `pending` con `next_attempt_at` nel passato viene ri-accodata una volta.
  `T-MAINT9` `test_pending_futura_ignorata` — con `next_attempt_at` fra un'ora, l'enqueuer non viene chiamato. Percorso negativo.
  `T-MAINT10` `test_sending_bloccata_recuperata` — una `sending` con `locked_at` di venti minuti fa torna `failed` e viene ri-accodata.
  `T-MAINT11` `test_sending_recente_non_toccata` — con `locked_at` di due minuti fa, lo stato resta `sending` e non c'e accodamento. Percorso negativo: e il test che impedisce al riconciliatore di duplicare gli invii in corso.
  `T-MAINT12` `test_dead_non_riaccodata` — una `dead` non viene mai ripescata automaticamente.
- **Done:** i cinque test passano.

### 8.5 Cancellazione degli oggetti e recupero degli orfani

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/tasks/maintenance.py` (modificato).
- **Pattern:** la coda `pending_object_deletions` e l'unico canale di cancellazione. Nessun altro punto del sistema chiama `delete_payload` (invariante I-8).
- **Change:**
  - `drain_object_deletions()` — legge fino a 500 righe da `pending_object_deletions` ordinate per `enqueued_at`, e per ciascuna:
    - chiama `delete_payload(storage_key)`;
    - se la cancellazione riesce, o se l'oggetto non esiste piu (l'assenza e il risultato voluto), rimuove la riga;
    - se fallisce per altri motivi, incrementa `attempts` e lascia la riga. Dopo 10 tentativi la riga resta e alimenta la metrica `pending_object_deletions_backlog`, che deve essere allarmabile.
    Aggiorna la gauge a fine esecuzione con il conteggio residuo.
  - `purge_orphan_objects()` — elenca gli oggetti del bucket con `list_objects_v2` paginato e, per ogni chiave con `LastModified` piu vecchio di 24 ore, verifica se esiste una riga `notifications` con quella `storage_key`. Se non esiste, cancella l'oggetto.
    **La verifica di esistenza attraversa i tenant**, e nessun ruolo puo farlo sotto RLS. Soluzione obbligatoria: la chiave contiene il `tenant_id` come primo segmento (formato definito in fase 5 sotto-fase 5.5), quindi il job lo estrae dalla chiave e apre `tenant_session_sync(tenant_id)` per interrogare. Se il primo segmento non e un UUID valido, la chiave non e stata prodotta da NotifyHub: **non cancellarla**, registrala nel log e passa oltre.
    La soglia di 24 ore evita di cancellare l'oggetto di una notifica il cui INSERT e ancora in corso.
- **Test strategy:** gli orfani si creano deliberatamente, caricando un oggetto senza riga corrispondente.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_object_maintenance.py` (marker `integration`):
  `T-MAINT13` `test_drain_cancella_e_svuota` — accodata una chiave esistente, dopo il job l'oggetto e sparito e la coda e vuota.
  `T-MAINT14` `test_drain_tollera_oggetto_gia_assente` — accodata una chiave inesistente, la riga viene rimossa comunque e il job non solleva.
  `T-MAINT15` `test_drain_conta_i_tentativi` — con `delete_payload` sostituito da una funzione che solleva, `attempts` passa a 1 e la riga resta. Percorso negativo.
  `T-MAINT16` `test_orfano_vecchio_cancellato` — un oggetto caricato con chiave valida, senza riga in tabella e con data simulata oltre 24 ore, viene rimosso.
  `T-MAINT17` `test_oggetto_referenziato_non_cancellato` — un oggetto con la sua riga `notifications` resta. E il percorso negativo piu importante della fase: fallisce se il job cancella payload validi.
  `T-MAINT18` `test_chiave_estranea_ignorata` — un oggetto con chiave `qualcosa/altro.txt`, il cui primo segmento non e un UUID, non viene cancellato.
- **Done:** i sei test passano. Verifica di autenticita: invertendo la condizione di `test_oggetto_referenziato_non_cancellato` il test deve diventare rosso.

### 8.6 Quote per tenant

- **Model:** Sonnet
- **Files:** `backend/app/services/quota.py` (nuovo), `backend/app/api/ingest.py` (modificato), `backend/app/tasks/maintenance.py` (modificato).
- **Pattern:** il conteggio giornaliero sta su Redis e non tocca il database a ogni ingestion; lo spazio occupato si ricalcola una volta a notte e si tiene su Redis.
- **Change:**
  - `app/services/quota.py` espone:
    ```python
    async def check_and_increment_daily(tenant_id: UUID, limit: int | None) -> bool
    async def check_storage(tenant_id: UUID, limit: int | None, incoming_bytes: int) -> bool
    ```
    `check_and_increment_daily` usa `INCR` sulla chiave `quota:daily:{tenant_id}:{yyyymmdd}` con TTL 172800 secondi; se `limit` e `None` restituisce `True` senza incrementare. Restituisce `False` quando il contatore supera il limite.
    `check_storage` legge `quota:usage:{tenant_id}`, scritta dal job notturno; se la chiave non esiste, la quota non viene applicata (fail-open deliberato: meglio accettare una notifica in piu che rifiutarla per un job che non ha ancora girato).
  - in `api/ingest.py`, inserisci il controllo delle quote **fra il passo 5 (limite per slug) e il passo 6 (risoluzione del modulo)** della tabella di fase 5 sotto-fase 5.7. Superata la quota -> `429` con `type=/problems/quota-exceeded` e `Retry-After` pari ai secondi mancanti alla mezzanotte UTC.
  - `recompute_tenant_usage()` — per ogni tenant somma `content_size` di tutte le notifiche e scrive il totale in `quota:usage:{tenant_id}` con TTL 172800 secondi.
- **Unit tests:** `backend/tests/unit/test_quota.py::test_limite_nullo_non_applicato` — con `limit=None` la funzione restituisce `True` senza toccare Redis (client finto che solleva se usato).
- **e2e tests:** in `backend/tests/integration/test_quota.py` (marker `integration`):
  `T-MAINT19` `test_quota_giornaliera_blocca` — con `max_notifications_per_day=2`, la terza ingestion restituisce `429` con `type` pari a `/problems/quota-exceeded`. Percorso negativo.
  `T-MAINT20` `test_quota_nulla_non_blocca` — con la colonna a `NULL`, cento ingestion passano tutte.
  `T-MAINT21` `test_usage_ricalcolato` — dopo `recompute_tenant_usage`, la chiave Redis contiene la somma esatta dei `content_size`.
- **Done:** i quattro test passano.

### 8.7 Metriche applicative complete

- **Model:** Haiku
- **Files:** `backend/app/api/ingest.py` (modificato), `backend/app/outbound/sender.py` (modificato), `backend/app/tasks/maintenance.py` (modificato).
- **Insertion point:** i collettori esistono gia in `backend/app/core/metrics.py` dalla fase 2 sotto-fase 2.5. Questa sotto-fase li **usa**, non ne dichiara di nuovi.
- **Change:**
  - in `api/ingest.py`: `ingest_requests_total` incrementato con l'etichetta corretta in ogni percorso di uscita (`created`, `replayed`, `not_found`, `too_large`, `rate_limited`, `error`); `ingest_body_bytes` osservato con `raw_size` sulle ingestion riuscite.
  - in `outbound/sender.py`: `deliveries_total` con etichetta `sent`, `failed` o `dead`; `delivery_latency_seconds` osservato sulla durata della chiamata HTTP.
  - in `maintenance.py`: `pending_object_deletions_backlog` impostata a fine di `drain_object_deletions`.
  Non aggiungere collettori nuovi. Se ne serve uno, **fermati e chiedi**.
- **Unit tests:** nessuno.
- **e2e tests:** `T-MAINT22` in `backend/tests/e2e/test_metrics.py::test_contatore_ingestion_cresce` — letto il valore di `ingest_requests_total{outcome="created"}` da `/metrics`, eseguita una ingestion, il valore e cresciuto di uno.
  `T-MAINT23` `test_contatore_not_found_cresce` — una chiamata con slug inesistente incrementa l'etichetta `not_found` e **non** l'etichetta `created`. Percorso negativo.
- **Done:** i due test passano; `make gates` verde.

---

## Files touched (this phase)

- `backend/app/tasks/celery_app.py` — modificato — `beat_schedule` con sette voci
- `backend/app/tasks/maintenance.py` — creato — i sette job
- `backend/app/services/quota.py` — creato — quota giornaliera e di spazio
- `backend/app/api/ingest.py` — modificato — controllo quote e metriche
- `backend/app/outbound/sender.py` — modificato — metriche di consegna
- `backend/tests/unit/test_beat_schedule.py`, `test_quota.py` — creati
- `backend/tests/integration/test_purge.py`, `test_reconcile.py`, `test_object_maintenance.py`, `test_quota.py` — creati
- `backend/tests/e2e/test_metrics.py` — modificato — due test nuovi

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** `T-CONS1` .. `T-CONS20`, `T-OUT1` .. `T-OUT26` restano verdi.

## Phase done criterion

`make gates` verde con `T-MAINT1` .. `T-MAINT23`. `T-MAINT17` dimostra che il recupero degli orfani non cancella payload validi; `T-MAINT11` che il riconciliatore non duplica gli invii in corso; `T-MAINT2` e `T-MAINT20` che le impostazioni nulle significano davvero "nessun limite".
