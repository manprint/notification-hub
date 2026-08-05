# Phase 0 — Backend: colonna `verified` + API toggle

> **Intent:** Aggiungere lo stato `verified` (bool) alle notifiche e abilitare il
> toggle read/unread/verified via `PATCH /api/v1/notifications/{id}`.
> **Shippable alone?** yes — nessuna modifica al frontend; l'API resta retro-compatibile.
> **Preconditions:** nessuna.

Il backend usa SQLAlchemy async + Alembic + FastAPI + Pydantic v2, con test
pytest (`asyncio_mode=auto`). Segui le convenzioni dei file citati: docstring
di modulo in italiano, migrazione manuale sparsa del template `0013`.

---

## Sub-phases

### 0.1 Model + migrazione `0014`
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; `agent-1` (stesso agente) rivede il data-model (gate design).
- **Files:** `backend/app/models/notification.py:99-101` (colonna `status`, aggiungi dopo); nuovo file `backend/alembic/versions/0014_notification_verified.py` (copialo morale da `backend/alembic/versions/0013_execution_phase.py`).
- **Change:**
  1. In `Notification` (`backend/app/models/notification.py`) aggiungi, subito DOPO la colonna `status` (riga 99-101):
     ```python
     # Flag di revisione manuale: l'operatore puo' contrassegnare una notifica
     # come verificata. Indipendente da status (unread/read). Default false.
     verified: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
     ```
     NOTE: la stringa `"false"` come `server_default` e' accettata da SQLAlchemy e genera `DEFAULT 'false'` in PG. `text` e' gia' importato (riga 13) ma NON serve qui.
  2. Crea `backend/alembic/versions/0014_notification_verified.py` con: `revision = "0014"`, `down_revision = "0013"`, `branch_labels = None`, `depends_on = None`. Docstring di modulo in italiano che spiega il flag.
  3. `upgrade()`: `op.add_column("notifications", sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")))`
  4. `downgrade()`: `op.drop_column("notifications", "verified")`
- **Unit tests:** nessun unit test dedicato (colonna pura).
- **e2e tests:** verranno in sub-phase 0.4.
- **Done:** `cd backend && ruff format --check . && ruff check . && mypy` verdi; la migrazione `0014` esiste con `revision="0014"` e `down_revision="0013"`. Non applicare ancora/obbligatoriamente; sul DB aggiornato con `make migrate-test` non deve dare errori.

### 0.2 Schemi Pydantic (`verified` in output, body PATCH esteso)
- **Model:** `backend/app/schemas/notification.py:29` (ListItemOut status), `:53` (DetailOut status), `:58-59` (MarkStatusIn).
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; agente-1 self-review della validazione body (gate accettazione).
- **Change:**
  1. In `NotificationListItemOut` (riga 29, dopo `status`) aggiungi: `verified: bool`.
  2. In `NotificationDetailOut` (riga 53, dopo `status`) aggiungi: `verified: bool`.
  3. Sostituisci `MarkStatusIn` (righe 58-59) con:
     ```python
     class MarkStatusIn(BaseModel):
         """Toggle di stato: almeno uno tra status e verified. Retro-compatibile:
         chi manda solo status (vecchi client) funziona identico."""
         status: NotificationStatus | None = None
         verified: bool | None = None

         @model_validator(mode="after")
         def _requires_at_least_one(self) -> "MarkStatusIn":
             if self.status is None and self.verified is None:
                 raise ValueError("at least one of 'status' or 'verified' is required")
             return self
     ```
  4. Aggiungi l'import `model_validator` dalla riga 4 gia' esistente `from pydantic import BaseModel, Field`: estendila a `from pydantic import BaseModel, Field, model_validator`.
- **Unit tests:** in `backend/tests/unit/test_notifications.py` (vedi sub-phase 0.4 per i nuovi nomi).
- **e2e tests:** sub-phase 0.4.
- **Done:** `ruff check` pulito; `MarkStatusIn()` solleva `pydantic.ValidationError`; `MarkStatusIn(verified=True).verified is True`; `MarkStatusIn(status="unread").status == "unread"`.

### 0.3 Handler API: lista, dettaglio, PATCH
- **Model:** `backend/app/api/v1/notifications.py:184` (lista), `:244` (dettaglio), `:303` (assign status), `:310-327` (response PATCH).
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; agente-1 self-review sull'hot-path PATCH (I-4).
- **Change:**
  1. In `list_notifications`, alla costruzione di `NotificationListItemOut` (righe 184-205) aggiungi `verified=n.verified,` accanto a `status=n.status,` (riga 198).
  2. In `get_notification_detail` (righe 244-261) e in `mark_notification_status` (righe 310-327) aggiungi `verified=notification.verified,` accanto a `status=...`.
  3. Nel body del PATCH (funzione `mark_notification_status`, riga 303-304) sostituisci il set incondizionato con:
     ```python
     if body.status is not None:
         notification.status = body.status
     if body.verified is not None:
         notification.verified = body.verified
     await session.flush()
     ```
     (sostituisce la sola riga `notification.status = body.status` + `flush`, righe 303-304). L'oggetto risposta della riga 310 aggiunge gia' `verified`.
- **Unit tests:** sub-phase 0.4.
- **e2e tests:** sub-phase 0.4.
- **Done:** le due response includono `verified`; un body `{"status":"read"}` non tocca `verified`; un body `{"verified":true}` non tocca `status`.

### 0.4 Test backend
- **Model:** `backend/tests/unit/test_notifications.py` (esistente, contiene `test_mark_status_schema` riga 33); nuovo file `backend/tests/e2e/test_notifications_verified.py`.
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; `agent-1` self-review delle asserzioni di accettazione.
- **Change (unit, in `test_notifications.py`, accanto a `test_mark_status_schema`):**
  1. `test_mark_status_accepts_verified_only` — `MarkStatusIn(verified=True)` e `assert body.verified is True` e `body.status is None`.
  2. `test_mark_status_rejects_empty_body` — `with pytest.raises(ValidationError): MarkStatusIn()`.
  3. Verificare che `test_mark_status_schema` (esistente, riga 33) resti verde SENZA modifiche.
- **Change (e2e, nuovo file `backend/tests/e2e/test_notifications_verified.py`):** copia i pattern di setup di `backend/tests/e2e/test_consumption.py:120-141` (fixture `api_client`, `two_tenants`, `owner_token`, an `ingest`/factory per creare una notifica). Aggiungi i test:
  - `T-VER1 test_patch_verified_persiste`: PATCH `{"verified": true}` -> 200; response `verified is True`; GET dettaglio riporta `verified is True`; status invariato (`unread` se era unread).
  - `T-VER2 test_toggle_status_torna_indietro_e_verified_ignora_unread_count`: segna `status=read`; poi PATCH `{"status":"unread"}` -> status torna `unread`; il `unread_count` della lista NON cambia dopo un PATCH `{"verified":true}` (e dopo averlo messo read e riportato, il conteggio torna com'era).
  - `T-VER3 test_patch_body_vuoto_422`: `json={}` -> 422.
  - `T-VER4 test_lista_e_dettaglio_espongono_verified_default_false`: una notifica creata di recente ha `verified == False` sia in lista sia in dettaglio.
  - Guardia I-4: il test e2e esistente `test_patch_segna_letta_e_bulk_read` (`test_consumption.py:120`) deve continuare a passare (non modificarlo).
- **Unit tests:** T-SCH1, test T-SCH2.
- **e2e tests:** T-VER1, T-VER2, T-VER3, T-VER4.
- **Done:** in `backend/`, con i servizi di test attivi (vedi gate), `pytest -q tests/unit/test_notifications.py tests/e2e/test_notifications_verified.py tests/e2e/test_consumption.py` verde.

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Types:** `make types`
- **Test subset:** `cd backend && pytest -q tests/unit/test_notifications.py` (unit, no servizi) e, con servizi su, `pytest -q tests/e2e/test_notifications_verified.py tests/e2e/test_consumption.py`
- **Regression guard:** T-I4: `test_mark_status_schema` (unit) + `test_bulk_mark_read` (e2e) devono restare verdi.

## Phase done criterion

`make gates` pulito e i quattro test e2e T-VER1..T-VER4 verdi (con `docker compose -f docker-compose.test.yml up -d` prima). La colonna `verified` esiste, l'API accetta i due toggle, i comportamenti pre-esistenti (mark read, bulk-read, validator status) restano invariati.