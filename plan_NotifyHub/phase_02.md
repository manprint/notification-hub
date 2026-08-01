# Fase 1 — Modello dati, migrazioni, Row Level Security

> **Intent:** portare a schema il modello della specifica sezione 4, con trigger, vincoli, indici, i quattro ruoli gia creati in fase 0 e le policy RLS della sezione 5, piu lo strato di sessione che imposta `app.tenant_id`.
> **Shippable alone?** si — al termine il database e completo e dimostrabilmente isolato, senza ancora alcun endpoint di dominio.
> **Preconditions:** fase 0 DONE. `make up-test` attivo.

Fonti autoritative: `notifyhub-spec.md` sezioni 4.1, 4.2, 4.3 per le tabelle; sezione 5.1, 5.2, 5.3 per policy e ruoli. **Le colonne, i tipi e i vincoli si copiano dalla specifica.** Questo file non li ripete: aggiunge solo le decisioni di implementazione che la specifica non fissa. Se una colonna del piano e della specifica divergono, vince la specifica; segnala la divergenza.

---

## Sub-phases

### 1.1 Base dichiarativa e convenzione dei nomi

- **Model:** Haiku
- **Files:** `backend/app/db/base.py` (nuovo).
- **Pattern:** `DeclarativeBase` di SQLAlchemy 2.0 con `MetaData(naming_convention=...)`. La convenzione dei nomi e obbligatoria: senza, Alembic genera nomi di vincolo instabili e le migrazioni successive diventano irriproducibili.
- **Change:** definisci `class Base(DeclarativeBase)` con:
  ```python
  metadata = MetaData(naming_convention={
      "ix": "ix_%(table_name)s_%(column_0_N_name)s",
      "uq": "uq_%(table_name)s_%(column_0_N_name)s",
      "ck": "ck_%(table_name)s_%(constraint_name)s",
      "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
      "pk": "pk_%(table_name)s",
  })
  ```
  Aggiungi due mixin riusabili nello stesso file:
  - `UUIDPrimaryKeyMixin` — colonna `id: Mapped[uuid.UUID]` con `primary_key=True`, `server_default=text("gen_random_uuid()")`;
  - `TimestampMixin` — `created_at` e `updated_at`, entrambe `timestamptz`, `server_default=func.now()`, `nullable=False`.
  `TimestampMixin` si applica **solo** alle tabelle di configurazione elencate nella specifica sezione 4 (tenants, users, groups, receivers, severity_rules, delivery_channels, group_channel_bindings, receiver_channel_overrides). Le altre tabelle hanno solo `created_at`.
- **Unit tests:** `backend/tests/unit/test_db_base.py::test_convenzione_nomi_presente` — asserisce che `Base.metadata.naming_convention["fk"]` sia esattamente la stringa sopra. Fallisce se qualcuno rimuove la convenzione.
- **e2e tests:** nessuno (nessun comportamento osservabile).
- **Done:** `make lint` e `make types` verdi; il modulo importa senza toccare il database.

### 1.2 Tipi enumerati

- **Model:** Haiku
- **Files:** `backend/app/db/types.py` (nuovo).
- **Change:** definisci gli enum Python (`enum.StrEnum`) e i corrispondenti tipi Postgres nativi. Nomi dei tipi SQL esatti: `tenant_status`, `user_role`, `user_status`, `receiver_status`, `severity`, `severity_source`, `notification_status`, `storage_backend`, `channel_type`, `override_mode`, `delivery_status`.

  **L'ordine di dichiarazione di `severity` e vincolante e non modificabile:** `('debug', 'info', 'warning', 'error', 'critical')`. Gli enum Postgres si confrontano secondo l'ordine di dichiarazione ed e cosi che funziona il confronto di soglia (specifica sezione 7). Non esiste alcuna funzione SQL di mappatura a intero: se la vedi comparire in una fase successiva, e un errore.

  Esporta anche `SEVERITY_ORDER: dict[Severity, int]` con `debug=10 … critical=50`, **usato solo dal codice Python** per ordinamenti e badge, mai tradotto in SQL.

  Ogni enum SQL va dichiarato con `postgresql.ENUM(..., name="<nome>", create_type=False)`: la creazione avviene nella migrazione, non all'import del modello.
- **Unit tests:** `backend/tests/unit/test_types.py::test_ordine_severity` — asserisce `list(Severity) == ["debug", "info", "warning", "error", "critical"]` e che `SEVERITY_ORDER["error"] > SEVERITY_ORDER["warning"]`. Fallisce se qualcuno riordina l'enum.
- **e2e tests:** nessuno.
- **Done:** `make types` verde.

### 1.3 Modelli di tenancy e identita

- **Model:** Sonnet
- **Files:** `backend/app/models/tenant.py`, `user.py`, `invitation.py`, `refresh_token.py` (tutti nuovi); `backend/app/models/__init__.py` (modificato: importa tutti i modelli in modo che `Base.metadata` sia completo).
- **Pattern:** un modulo per aggregato, `Mapped[...]` con `mapped_column(...)` tipizzato. **Tutte le relazioni sono dichiarate con `lazy="raise"`** (decisione D9): con sessioni async il caricamento pigro esplode a runtime, meglio un errore immediato in test.
- **Change:** riproduci le quattro tabelle della specifica sezione 4.1, colonna per colonna. Dettagli che la specifica non fissa e che vanno rispettati:
  - `users.email` e `invitations.email` usano il tipo `CITEXT` (`sqlalchemy.dialects.postgresql.CITEXT`). L'estensione viene creata dalla migrazione 1.6.
  - `users.email` porta un vincolo di unicita **globale**, non composito con `tenant_id`: e la decisione della specifica sezione 4.1.
  - `tenants` include `max_notifications_per_day` e `max_storage_bytes`, entrambe nullable, presenti da subito anche se l'enforcement arriva in fase 8.
  - `refresh_tokens.token_hash` e `invitations.token_hash` sono `text` con unicita.
  - nessuna colonna contiene segreti in chiaro (invariante I-6).
- **Test strategy:** test unitari di metadata, senza database: si ispeziona `Base.metadata.tables`.
- **Unit tests:** in `backend/tests/unit/test_models_identity.py`:
  `test_email_utente_unica_globalmente` — cerca fra i vincoli di `users` un `UniqueConstraint` sulle sole colonne `("email",)` e asserisce che esista; asserisce inoltre che **non** esista un vincolo su `("tenant_id", "email")`. Fallisce se qualcuno reintroduce l'unicita per tenant.
  `test_tenant_ha_colonne_quota` — asserisce la presenza di `max_notifications_per_day` e `max_storage_bytes`.
  `test_relazioni_non_lazy` — per ogni relazione dichiarata nei quattro modelli asserisce `rel.lazy == "raise"`.
- **e2e tests:** nessuno.
- **Done:** `make types` verde; i tre test unitari passano.

### 1.4 Modelli di dominio delle notifiche

- **Model:** Sonnet
- **Files:** `backend/app/models/group.py`, `receiver.py`, `severity_rule.py`, `notification.py` (nuovi); `backend/app/models/__init__.py` (modificato).
- **Change:** riproduci le quattro tabelle della specifica sezione 4.2. Dettagli vincolanti:
  - **`notifications.metadata`**: la colonna SQL si chiama `metadata`, ma `metadata` e un attributo riservato in SQLAlchemy declarative. Il mapping obbligatorio e
    ```python
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ```
    Usare `metadata` come nome dell'attributo Python fa fallire l'import della classe. Se lo vedi scritto cosi, e un errore.
  - `notifications.id` non ha `server_default`: l'id viene generato in Python con `uuid.uuid4()` perche entra nella chiave dell'oggetto MinIO prima dell'INSERT (specifica sezione 6.5 punto 5). Su questa sola tabella il mixin `UUIDPrimaryKeyMixin` **non** si applica: dichiara la colonna esplicitamente con `default=uuid.uuid4`.
  - `notifications.content_preview` e `NOT NULL`; `content` e `storage_key` sono nullable e mutualmente esclusive, vincolo aggiunto in 1.7.
  - `notifications.content_normalized` e `boolean NOT NULL DEFAULT false`.
  - `receivers.slug` e `String(22)`, unico globalmente, indicizzato.
  - `severity_rules.pattern` e `String(200)`: il limite di lunghezza e una difesa in profondita citata nella specifica sezione 4.2.
  - nessuna tabella dichiara indici qui: gli indici stanno nella migrazione 1.7, in un punto solo.
- **Unit tests:** in `backend/tests/unit/test_models_domain.py`:
  `test_colonna_metadata_mappata_come_meta` — asserisce che `Notification.meta.property.columns[0].name == "metadata"` e che `hasattr(Notification, "metadata") is False` a livello di istanza mappata.
  `test_notification_id_generato_in_python` — asserisce che la colonna `id` di `notifications` abbia un `default` Python e nessun `server_default`.
  `test_pattern_lunghezza_massima` — asserisce `severity_rules.c.pattern.type.length == 200`.
- **e2e tests:** nessuno.
- **Done:** `make types` verde; i tre test passano; `python -c "from app.models import *"` da `backend/` non solleva eccezioni.

### 1.5 Modelli outbound e coda di cancellazione oggetti

- **Model:** Sonnet
- **Files:** `backend/app/models/channel.py`, `binding.py`, `delivery.py`, `object_deletion.py` (nuovi); `backend/app/models/__init__.py` (modificato).
- **Change:** riproduci le tabelle della specifica sezione 4.3 piu `pending_object_deletions` della sezione 6.5. Dettagli vincolanti:
  - `delivery_channels.webhook_url` e `LargeBinary` (bytea): contiene il ciphertext AES-GCM, mai testo. Il modello **non** espone alcuna proprieta che decifri: la decifratura sta in `app/core/crypto.py` (fase 2) ed e chiamata esplicitamente da chi ne ha diritto.
  - `binding.py` contiene entrambe le tabelle `group_channel_bindings` e `receiver_channel_overrides`: sono lo stesso concetto e stanno nello stesso modulo.
  - `deliveries` include `locked_at` nullable e il vincolo di unicita su `(notification_id, channel_id)`.
  - `pending_object_deletions` **non ha `tenant_id`** ed e l'unica tabella di dominio fuori da RLS.
- **Unit tests:** in `backend/tests/unit/test_models_outbound.py`:
  `test_webhook_url_e_binario` — asserisce che il tipo della colonna sia `LargeBinary`; fallisce se qualcuno la trasforma in `Text`, che romperebbe l'invariante I-6.
  `test_unicita_delivery` — asserisce l'esistenza di un `UniqueConstraint` su `("notification_id", "channel_id")`.
  `test_pending_object_deletions_senza_tenant` — asserisce che la tabella non abbia la colonna `tenant_id`.
- **e2e tests:** nessuno.
- **Done:** `make types` verde; `Base.metadata.tables` contiene esattamente 13 tabelle: tenants, users, invitations, refresh_tokens, groups, receivers, severity_rules, notifications, delivery_channels, group_channel_bindings, receiver_channel_overrides, deliveries, pending_object_deletions.

### 1.6 Alembic e prima migrazione dello schema

- **Model:** Sonnet
- **Files:** `backend/alembic.ini` (nuovo), `backend/alembic/env.py` (nuovo), `backend/alembic/versions/0001_schema_iniziale.py` (nuovo).
- **Pattern:** Alembic in modalita sincrona. Anche se l'applicazione usa engine async, le migrazioni girano con `psycopg`: e piu semplice e non richiede `run_sync`.
- **Change:**
  - `alembic/env.py` legge `DATABASE_URL_OWNER` dall'ambiente (rispettando `ENV_FILE`), converte lo schema `postgresql+asyncpg` in `postgresql+psycopg` prima di connettersi, importa `app.models` e usa `Base.metadata` come `target_metadata`. Imposta `compare_type=True` e `include_schemas=False`.
  - La migrazione `0001` fa, in questo ordine: `CREATE EXTENSION IF NOT EXISTS citext`; creazione dei tipi enumerati elencati in 1.2 con `sa.Enum(..., name=...).create(bind)`; creazione delle 13 tabelle. Nessun indice oltre a quelli impliciti di chiave primaria e unicita, nessun trigger, nessuna policy: arrivano in 1.7 e 1.8.
  - **Le migrazioni non inseriscono dati.** Con `FORCE ROW LEVEL SECURITY` anche il proprietario e soggetto alle policy: un seeding dentro la migrazione fallirebbe. Il primo tenant si crea con la CLI di fase 3.
- **Test strategy:** verifica che `upgrade head` e `downgrade base` siano entrambi eseguibili sul database di test, cosi la migrazione resta reversibile.
- **Unit tests:** nessuno.
- **e2e tests:** `T-DDL1` in `backend/tests/integration/test_migrations.py::test_upgrade_e_downgrade` (marker `integration`) — esegue programmaticamente `alembic upgrade head` poi `downgrade base` poi di nuovo `upgrade head` contro `notifyhub_test`, asserendo che nessuno dei tre passaggi sollevi eccezioni e che al termine esistano 13 tabelle in `information_schema.tables` per lo schema `public`.
- **Done:** `make migrate-test` termina con exit 0; `T-DDL1` verde.

### 1.7 Migrazione di indici, vincoli e trigger

- **Model:** Sonnet
- **Files:** `backend/alembic/versions/0002_indici_vincoli_trigger.py` (nuovo).
- **Change:** una sola migrazione con quattro blocchi, nell'ordine:
  1. **Vincolo di coerenza del corpo** — il `CHECK` `ck_notifications_body` riportato testualmente nella specifica sezione 4.2.
  2. **Indici** — esattamente quelli elencati nella specifica: i cinque su `notifications` (sezione 4.2), `ix_receivers_tenant_id_group_id` e l'indice parziale su `severity_rules` (sezione 4.2), i tre su `deliveries` (sezione 4.3). Nessun indice inventato.
  3. **Trigger `updated_at`** — funzione `set_updated_at()` in PL/pgSQL che assegna `NEW.updated_at = now()` e restituisce `NEW`, piu un trigger `BEFORE UPDATE FOR EACH ROW` su ciascuna delle otto tabelle di configurazione elencate in 1.1.
  4. **Trigger di cancellazione oggetti** — funzione `enqueue_object_deletion()` che, se `OLD.storage_backend = 'object'`, inserisce `OLD.storage_key` in `pending_object_deletions`; trigger `AFTER DELETE FOR EACH ROW` su `notifications`. Questo trigger e cio che realizza l'invariante I-8 per tutti i percorsi di cancellazione, compreso il `CASCADE`.

  `downgrade` rimuove tutto in ordine inverso.
- **Test strategy:** i trigger si verificano con effetti osservabili sul database di test, non ispezionando il catalogo.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_triggers.py` (marker `integration`, esegue come `notifyhub_owner` con RLS ancora non attiva a questo punto della sequenza di test):
  `T-DDL2` `test_updated_at_si_aggiorna` — inserisce un tenant, legge `updated_at`, aggiorna `name`, rilegge e asserisce che `updated_at` sia cresciuto. Test negativo implicito: senza il trigger il valore resta identico e il test fallisce.
  `T-DDL3` `test_cancellazione_oggetto_accodata` — inserisce una notification con `storage_backend='object'` e `storage_key='k/1.txt'`, la cancella, asserisce che `pending_object_deletions` contenga esattamente una riga con quella chiave.
  `T-DDL4` `test_cancellazione_inline_non_accodata` — stessa cosa con `storage_backend='inline'`, asserisce zero righe accodate. Impedisce un trigger scritto troppo largo.
  `T-DDL5` `test_check_corpo_rifiuta_incoerenza` — tenta l'inserimento di una notification con `storage_backend='object'` e `content` valorizzato; asserisce che il database sollevi `IntegrityError`.
- **Done:** i quattro test passano; `make migrate-test` resta idempotente su una seconda esecuzione.

### 1.8 Migrazione di GRANT e policy RLS

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/alembic/versions/0003_rls.py` (nuovo).
- **Pattern:** la migrazione emette SQL testuale con `op.execute`. Non esiste supporto nativo di Alembic per le policy: e corretto e voluto.
- **Change:** quattro blocchi, nell'ordine.

  1. **GRANT di runtime.**
     - `notifyhub_app`: `SELECT, INSERT, UPDATE, DELETE` su tutte le tabelle tranne nessuna, piu `USAGE` sullo schema. Include `tenants` e `pending_object_deletions`.
     - `notifyhub_ingest`: **solo** `SELECT` su `receivers`. Nient'altro, su nessuna altra tabella.
     - `notifyhub_auth`: **solo** `SELECT` su `users`, `refresh_tokens`, `invitations`. Nient'altro.
     Nessun `GRANT ALL`, nessun `GRANT ... ON ALL TABLES` per i due ruoli ristretti.

  2. **RLS su tutte le tabelle con `tenant_id`** — undici tabelle: users, invitations, refresh_tokens, groups, receivers, severity_rules, notifications, delivery_channels, group_channel_bindings, receiver_channel_overrides, deliveries. Per ciascuna:
     ```sql
     ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
     ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
     CREATE POLICY tenant_isolation ON <t>
       USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
       WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
     ```
     Il secondo argomento `true` di `current_setting` e obbligatorio: senza, la funzione solleva `unrecognized configuration parameter` invece di restituire NULL, e ogni query fuori dal contesto autenticato esplode. Il `NULLIF` copre il caso in cui la GUC sia impostata a stringa vuota. Con GUC assente il confronto vale NULL, quindi zero righe visibili e zero righe scrivibili: il default e il diniego.

  3. **Policy dei ruoli ristretti**, esattamente come nella specifica sezione 5.2:
     ```sql
     CREATE POLICY ingest_slug_lookup ON receivers      FOR SELECT TO notifyhub_ingest USING (true);
     CREATE POLICY auth_lookup        ON users          FOR SELECT TO notifyhub_auth   USING (true);
     CREATE POLICY auth_lookup        ON refresh_tokens FOR SELECT TO notifyhub_auth   USING (true);
     CREATE POLICY auth_lookup        ON invitations    FOR SELECT TO notifyhub_auth   USING (true);
     ```
     Sono sicure perche i due ruoli non hanno alcun privilegio di scrittura e l'applicazione li interroga solo per chiave univoca.

  4. **`tenants` e `pending_object_deletions` restano senza RLS**, come stabilisce la specifica. L'isolamento su `tenants` e applicativo: ogni query filtra per `id`. Aggiungi in cima alla migrazione un commento di tre righe che lo dichiari, cosi nessuno lo scambia per una dimenticanza.

  > **Attenzione, cambio di comportamento.** Dopo questa migrazione ogni test che scriveva sul database senza impostare `app.tenant_id` smette di funzionare. I test di integrazione delle sotto-fasi 1.6 e 1.7 girano come `notifyhub_owner`: `FORCE ROW LEVEL SECURITY` li sottopone comunque alle policy. Vanno adeguati in 1.10 usando la fixture `tenant_session`. Questo adeguamento e previsto e non e una regressione.
- **Test strategy:** la verifica sostanziale e in 1.10. Qui si verifica solo che nessun ruolo abbia privilegi in eccesso.
- **Unit tests:** nessuno.
- **e2e tests:** `T-RLS1` in `backend/tests/integration/test_privilegi.py::test_ruoli_ristretti_senza_scrittura` (marker `integration`) — interroga `information_schema.role_table_grants` e asserisce che per `notifyhub_ingest` esista una sola riga (`SELECT` su `receivers`) e che per `notifyhub_auth` esistano esattamente tre righe, tutte `SELECT`. Fallisce se qualcuno allarga una GRANT.
  `T-RLS2` `test_nessun_ruolo_bypassa_rls` — interroga `pg_roles` e asserisce `rolbypassrls = false` per tutti e quattro i ruoli `notifyhub_*`. E il test che protegge l'invariante I-1.
- **Done:** `make migrate-test` verde; `T-RLS1` e `T-RLS2` passano.

### 1.9 Strato di sessione e impostazione di `app.tenant_id`

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/db/session.py` (nuovo), `backend/app/db/sync_session.py` (nuovo).
- **Pattern:** tre engine async separati, uno per ruolo, piu un engine sincrono per Celery. Un context manager per ciascun tipo di accesso. Nessun codice di dominio crea sessioni da solo: passa sempre da qui.
- **Change:** `session.py` espone:
  - `engine_app`, `engine_auth`, `engine_ingest`: `create_async_engine` sui rispettivi URL, `pool_pre_ping=True`, `echo=False`;
  - `@asynccontextmanager async def tenant_session(tenant_id: UUID) -> AsyncIterator[AsyncSession]` — apre una sessione su `engine_app`, inizia la transazione, esegue
    ```python
    await session.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})
    ```
    e la cede al chiamante; al termine committa, oppure fa rollback in caso di eccezione. `SET LOCAL` muore con la transazione: nessun residuo sul pool.
  - `@asynccontextmanager async def auth_session() -> AsyncIterator[AsyncSession]` — sessione di sola lettura su `engine_auth`, senza alcuna GUC.
  - `@asynccontextmanager async def ingest_session() -> AsyncIterator[AsyncSession]` — sessione di sola lettura su `engine_ingest`, senza alcuna GUC.

  `sync_session.py` espone `sync_engine` (`create_engine` su `DATABASE_URL_SYNC`, driver `psycopg`) e `@contextmanager def tenant_session_sync(tenant_id: UUID)` con la stessa semantica, per i task Celery (specifica sezione 8.4).

  Il parametro di `SET LOCAL` va passato come bind parameter, mai interpolato in stringa: `app.tenant_id` arriva da un claim JWT ed e input esterno.
- **Test strategy:** i test coprono il comportamento della GUC, non l'implementazione.
- **Unit tests:** nessuno (richiedono il database).
- **e2e tests:** coperti da 1.10.
- **Done:** `make types` verde; i tre context manager importabili senza connessione.

### 1.10 Suite di isolamento RLS

- **Model:** Opus design review sulle asserzioni -> Sonnet implementa
- **Files:** `backend/tests/conftest.py` (modificato: si aggiungono le fixture di database), `backend/tests/integration/test_rls.py` (nuovo), `backend/tests/integration/test_triggers.py` (modificato per usare le nuove fixture).
- **Insertion point:** in `conftest.py`, dopo la fixture `api_client` creata in fase 0 sotto-fase 0.7.
- **Pattern:** ogni test crea i propri tenant con id generati in Python, cosi non serve alcuna pulizia globale; la fixture di funzione cancella al termine cio che ha creato.
- **Change:** aggiungi in `conftest.py`:
  - fixture di sessione `migrated_db` — esegue `alembic upgrade head` una volta per l'intera sessione di test;
  - fixture di funzione `owner_conn` — connessione con `notifyhub_owner`, usata solo per creare le righe `tenants` (tabella fuori da RLS) e per la pulizia;
  - fixture di funzione `two_tenants` — crea due tenant `A` e `B` e restituisce i loro UUID;
  - factory `make_user(tenant_id, ...)` che inserisce un utente dentro `tenant_session(tenant_id)`.

  `test_rls.py` contiene i test seguenti, tutti con marker `integration`. Sono la dimostrazione dell'invariante I-1 e vanno scritti con cura.

  | ID | Test | Asserzione |
  |----|------|-----------|
  | `T-RLS3` | `test_lettura_isolata_fra_tenant` | Creati un utente in A e uno in B, una `tenant_session(A)` che fa `SELECT` su `users` vede una sola riga, quella di A |
  | `T-RLS4` | `test_lettura_senza_guc_non_vede_nulla` | Una sessione su `engine_app` **senza** `SET LOCAL` restituisce zero righe da `users`, e non solleva eccezione. Questo e il test che dimostra il diniego di default e fallirebbe se `current_setting` fosse scritto senza il secondo argomento |
  | `T-RLS5` | `test_scrittura_con_tenant_sbagliato_rifiutata` | Dentro `tenant_session(A)`, l'INSERT di una riga con `tenant_id = B` solleva un errore di violazione della policy `WITH CHECK` |
  | `T-RLS6` | `test_update_non_attraversa_i_tenant` | Dentro `tenant_session(A)`, un `UPDATE users SET status='disabled'` senza clausola `WHERE` modifica zero righe di B |
  | `T-RLS7` | `test_ruolo_ingest_legge_solo_receivers` | Con `ingest_session()`, la `SELECT` su `receivers` per slug funziona senza GUC; la `SELECT` su `notifications` fallisce per privilegio insufficiente |
  | `T-RLS8` | `test_ruolo_auth_non_puo_scrivere` | Con `auth_session()`, la `SELECT` su `users` per email funziona; un `INSERT` su `users` fallisce per privilegio insufficiente |
  | `T-RLS9` | `test_guc_non_persiste_fra_transazioni` | Aperta e chiusa una `tenant_session(A)`, una successiva sessione nuda sullo stesso pool vede zero righe: `SET LOCAL` non e sopravvissuto |

  Adegua `test_triggers.py` perche usi `tenant_session` invece della connessione nuda: e il cambio di comportamento annunciato in 1.8.
- **Unit tests:** nessuno.
- **e2e tests:** i sette test in tabella.
- **Done:** `make test-int` verde con tutti i test da `T-RLS1` a `T-RLS9` e da `T-DDL1` a `T-DDL5`. Verifica di autenticita: commentando la riga `SET LOCAL` in `tenant_session`, almeno `T-RLS3`, `T-RLS6` e `T-RLS9` devono diventare rossi. Esegui questa verifica, poi ripristina.

---

## Files touched (this phase)

- `backend/app/db/base.py` — creato — Base dichiarativa, convenzione nomi, mixin
- `backend/app/db/types.py` — creato — enum Python e tipi Postgres
- `backend/app/db/session.py` — creato — tre engine async e i context manager
- `backend/app/db/sync_session.py` — creato — engine sincrono per Celery
- `backend/app/models/tenant.py`, `user.py`, `invitation.py`, `refresh_token.py` — creati — tenancy
- `backend/app/models/group.py`, `receiver.py`, `severity_rule.py`, `notification.py` — creati — dominio
- `backend/app/models/channel.py`, `binding.py`, `delivery.py`, `object_deletion.py` — creati — outbound
- `backend/app/models/__init__.py` — modificato — importa tutti i modelli
- `backend/alembic.ini` — creato — configurazione Alembic
- `backend/alembic/env.py` — creato — contesto di migrazione
- `backend/alembic/versions/0001_schema_iniziale.py` — creato — estensione, enum, 13 tabelle
- `backend/alembic/versions/0002_indici_vincoli_trigger.py` — creato — CHECK, indici, due trigger
- `backend/alembic/versions/0003_rls.py` — creato — GRANT e policy
- `backend/tests/conftest.py` — modificato — fixture di database
- `backend/tests/unit/test_db_base.py`, `test_types.py`, `test_models_identity.py`, `test_models_domain.py`, `test_models_outbound.py` — creati
- `backend/tests/integration/test_migrations.py`, `test_triggers.py`, `test_privilegi.py`, `test_rls.py` — creati

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** `T-ENV1`, `T-SCAF1`, `T-SCAF2`, `T-SCAF3`, `T-SCAF4`, `T-SCAF5` restano verdi.

## Phase done criterion

`make gates` verde con la suite completa. `T-RLS2` dimostra che nessun ruolo ha `BYPASSRLS`; `T-RLS4` e `T-RLS9` dimostrano che il diniego e il comportamento predefinito; `T-DDL3` e `T-DDL4` dimostrano che l'accodamento delle cancellazioni scatta solo per i payload su object store. La verifica di autenticita descritta in 1.10 e stata eseguita e i test giusti sono diventati rossi.
