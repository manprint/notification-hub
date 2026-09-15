# Specifica Funzionale e Tecnica — NotifyHub

Versione: 0.3 (bozza di sviluppo — decisioni chiuse)
Stato: nessun punto architetturale aperto. Le sezioni marcate ⚠️ sono rischi noti o rimandi consapevoli, non domande.
Data: 2026-08-01

---

## 1. Obiettivo e scope

NotifyHub è un aggregatore di notifiche multi-tenant self-hosted.

Fa tre cose:

1. **Ingestion** — riceve notifiche da fonti esterne (v1: HTTP testo semplice via `curl`/`wget`) su endpoint univoci chiamati **Receiver**, con architettura a moduli per accogliere canali futuri (email, Telegram, MQTT, webhook JSON) senza toccare il core.
2. **Consultazione** — dashboard web con filtri per gruppo, receiver, severità e stato di lettura.
3. **Inoltro (outbound)** — rilancia le notifiche verso **Google Chat** e **Slack** quando superano una soglia di severità configurabile.

Fuori scope per la v1: app mobile, notifiche push native, canali outbound diversi da Slack/Google Chat, azioni interattive dai messaggi inoltrati, digest schedulati, ricerca full-text dentro i payload offloaded.

---

## 2. Scelte architetturali portanti

| Area | Decisione |
|---|---|
| Backend | Python 3.12 + FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic |
| Frontend | React + TypeScript + Vite (SPA separata) |
| Database | PostgreSQL 16 |
| Object storage | **MinIO** (S3-compatible) — payload di ingestion oltre 1MB salvati su bucket, in tabella resta solo il riferimento |
| Multi-tenancy | Schema condiviso + `tenant_id` + **Row Level Security**, tre ruoli Postgres, **nessun ruolo con `BYPASSRLS`** |
| Identità | Email **unica globalmente**: un account appartiene a un solo tenant |
| Autenticazione | JWT access token (15 min) + refresh token rotante (30 gg) |
| Job asincroni | Celery + Redis. Worker con **sessione SQLAlchemy sincrona** dedicata (l'API resta async) |
| Motore regex | `google-re2` — tempo di esecuzione lineare, ReDoS strutturalmente impossibile |
| Outbound | Solo Incoming Webhook URL (Slack + Google Chat), nessun OAuth |
| Trigger inoltro | Soglia di severità |
| Real-time dashboard | Polling REST nell'MVP, SSE in v2 |
| Retention | Purge automatico configurabile per tenant |
| Deploy | Docker Compose self-hosted. SMTP **opzionale** |

---

## 3. Entità e relazioni

```
Tenant (1) ─┬─ (N) User
            ├─ (N) Group (1) ── (N) Receiver (1) ── (N) Notification
            │                        └── (N) SeverityRule
            └─ (N) DeliveryChannel

Group (N) ──── (N) DeliveryChannel        [via GroupChannelBinding]
Receiver (N) ── (N) DeliveryChannel       [via ReceiverChannelOverride]
Notification (1) ── (N) Delivery          [outbox di inoltro]
```

- Un **Receiver** appartiene a un solo **Group** (1:N confermato, no N:N)
- Una **Notification** appartiene a un solo **Receiver**
- Un **User** appartiene a un solo **Tenant** (email unica globale)
- Ogni riga di ogni tabella appartiene a un solo **Tenant**

### Glossario

| Termine | Significato |
|---|---|
| Tenant | Organizzazione proprietaria dei dati. Confine di isolamento |
| User | Account che accede al management, appartiene a un Tenant con un ruolo |
| Group | Contenitore logico di Receiver correlati (es. "Server Produzione") |
| Receiver | Endpoint univoco identificato da uno slug, verso cui si inviano notifiche |
| Slug | Identifica il Receiver nell'URL: `gruppo-receiver-token`, dove il token e' urlsafe di 22 caratteri generato random (l'unica parte che vale come credenziale) |
| Notification | Singolo messaggio ricevuto da un Receiver |
| Severity | Livello di gravità: `debug` < `info` < `warning` < `error` < `critical` |
| SeverityRule | Regola regex (sintassi RE2) sul contenuto che assegna una severity |
| Ingestion Module | Componente che interpreta un formato/canale in arrivo e produce una Notification standard |
| Payload offloaded | Contenuto oltre `INLINE_MAX_BYTES`, persistito su MinIO e referenziato da `storage_key` |
| DeliveryChannel | Destinazione di inoltro (webhook Slack o Google Chat) |
| Delivery | Tentativo di inoltro di una Notification verso un Channel. Riga di outbox |

---

## 4. Modello dati

Tutte le tabelle (tranne `tenants` e `pending_object_deletions`) hanno `tenant_id UUID NOT NULL` con policy RLS. Tutte hanno `id UUID PK` (default `gen_random_uuid()`) e `created_at timestamptz NOT NULL DEFAULT now()`.

**`updated_at timestamptz NOT NULL DEFAULT now()`** è presente sulle sole tabelle di configurazione — `tenants`, `users`, `groups`, `receivers`, `severity_rules`, `delivery_channels`, `group_channel_bindings`, `receiver_channel_overrides` — mantenuto da un trigger `BEFORE UPDATE`. Non è presente su `notifications` e `deliveries`, che hanno già timestamp propri e volumi tali da non giustificare la scrittura in più.

### 4.1 Tenancy e identità

#### `tenants`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| name | text | ragione sociale / nome team |
| slug | text unique | usato in URL di invito |
| max_body_bytes | int | **cap massimo** che un receiver del tenant può configurare. Default 1.048.576 (1MB), hard limit di sistema 20.971.520 (20MB) |
| max_notifications_per_day | int NULL | quota giornaliera. NULL = illimitata. **Colonna presente da F1, enforcement in F7** |
| max_storage_bytes | bigint NULL | spazio complessivo (inline + oggetti MinIO). NULL = illimitato. **Colonna presente da F1, enforcement in F7** |
| retention_days | int NULL | NULL = nessun purge automatico. Default 90 |
| status | enum(active, suspended) | |
| created_at, updated_at | timestamptz | |

#### `users`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK → tenants.id | |
| email | citext | **unique globale** — non per tenant. Rende il login non ambiguo |
| password_hash | text | Argon2id |
| role | enum(owner, admin, member, viewer) | |
| status | enum(active, disabled) | |
| last_login_at | timestamptz NULL | |
| created_at, updated_at | timestamptz | |

> L'unicità globale dell'email significa che una persona non può appartenere a due tenant con lo stesso indirizzo. È una limitazione accettata: elimina l'ambiguità del login e il bisogno di uno step "scegli organizzazione". Il percorso di evoluzione, se un giorno servisse, è una tabella `memberships` — non una modifica dell'architettura.

**Matrice ruoli** (autorizzazione applicata a livello di dependency FastAPI, oltre a RLS)

| Azione | owner | admin | member | viewer |
|---|:-:|:-:|:-:|:-:|
| Gestire tenant (retention, cap body, quote) | ✅ | ❌ | ❌ | ❌ |
| Invitare / rimuovere utenti, cambiare ruoli | ✅ | ✅ | ❌ | ❌ |
| CRUD Group / Receiver / Channel / SeverityRule | ✅ | ✅ | ✅ | ❌ |
| Rigenerare lo slug di un Receiver | ✅ | ✅ | ❌ | ❌ |
| Vedere l'elenco dei DeliveryChannel (URL mascherato) | ✅ | ✅ | ✅ | ❌ |
| Consultare `/deliveries` (diagnostica inoltri) | ✅ | ✅ | ✅ | ✅ |
| Ri-accodare una delivery `dead` | ✅ | ✅ | ✅ | ❌ |
| Leggere notifiche, segnare come lette / non lette e come verificate / non verificate | ✅ | ✅ | ✅ | ✅ |
| Eliminare notifiche | ✅ | ✅ | ✅ | ❌ |

Il rotate-slug resta ad admin+ anche se il `member` può creare receiver: rigenerare uno slug rompe gli script già in produzione sui server dei clienti.

**Vincolo ultimo owner** — è vietato rimuovere o declassare l'ultimo utente `owner` attivo di un tenant. `DELETE /users/{id}` e `PATCH /users/{id}` rispondono `409 Conflict` (`type: /problems/last-owner`). Il vincolo è verificato applicativamente dentro la stessa transazione, con `SELECT … FOR UPDATE` sulla riga del tenant per evitare la race di due rimozioni concorrenti.

#### `invitations`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| email | citext | |
| role | enum | ruolo assegnato all'accettazione |
| token_hash | text unique | SHA-256 del token; il token in chiaro non è mai persistito né messo in un URL path |
| expires_at | timestamptz | default +7 giorni |
| accepted_at | timestamptz NULL | |
| invited_by | FK → users.id | |

#### `refresh_tokens`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| user_id | FK → users.id | |
| token_hash | text unique | |
| family_id | UUID | per la rotazione: riuso di un token già ruotato ⇒ revoca dell'intera famiglia |
| expires_at | timestamptz | default +30 giorni |
| revoked_at | timestamptz NULL | |
| user_agent, ip | text NULL | audit sessioni |

### 4.2 Dominio notifiche

#### `groups`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| name | text | unique per `(tenant_id, name)` |
| description | text NULL | |
| created_at, updated_at | timestamptz | |

#### `receivers`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| group_id | FK → groups.id | NOT NULL, `ON DELETE CASCADE` |
| slug | text(120) unique **globale**, indexed | `{gruppo}-{receiver}-{token}`, dove il token è `secrets.token_urlsafe(16)` ⇒ 128 bit di entropia |
| name | text | etichetta leggibile |
| status | enum(active, disabled) | `disabled` ⇒ ingestion rifiutata con **404**, vedi §9.1 |
| ingestion_module | text | default `http_raw` |
| default_severity | enum(debug…critical) | default `info`. Ultimo anello della catena di severity |
| max_body_bytes | int | **configurabile per receiver**. Validato a ≤ `tenants.max_body_bytes` |
| rate_limit_per_min | int | default 60. **0 = nessun limite per-slug**; il limite per IP resta comunque attivo |
| expected_every_seconds | int NULL | sorveglianza dell'attesa: intervallo fra un invio e il successivo |
| expected_cron | text(100) NULL | alternativa all'intervallo: espressione cron a 5 campi, come in crontab |
| expected_timezone | text(64) NULL | fuso dell'espressione cron (default `UTC`); solo con `expected_cron` |
| expected_grace_seconds | int NULL | tolleranza sul ritardo |
| missing_severity | enum NULL | severity della notifica di assenza. NULL su tutti = sorveglianza spenta (CHECK `ck_receivers_expected_policy`) |
| last_start_at | timestamptz NULL | ultimo ping di avvio (`X-Phase: start`). Separato dalla conclusione: distingue "non e partito" da "partito e mai finito" |
| expected_since | timestamptz NULL | da quando la politica e in vigore: riferimento per un receiver che non ha mai ricevuto |
| last_notification_at | timestamptz NULL | ultimo invio **vero**, denormalizzato dall'ingestion (le notifiche sintetiche non lo toccano) |
| missing_alerted_at | timestamptz NULL | assenza gia segnalata: una notifica per assenza, riarmata al primo invio vero |
| created_at, updated_at | timestamptz | |

```sql
CREATE INDEX ON receivers (tenant_id, group_id);   -- filtro group_id delle notifiche
```

> Lo slug è unique globalmente e non per tenant: l'URL `/ingest/{slug}` deve risolvere senza contesto di tenant.

**Forma dello slug** — `maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ`: nome del gruppo, nome del receiver (ridotti a `[a-z0-9-]`, max 32 caratteri ciascuno, omessi se non traducibili) e in coda il token casuale di 22 caratteri, che è l'unica parte che vale come credenziale. Il prefisso rende leggibile una riga di crontab o un log di nginx, e non tocca l'entropia.

Il prefisso è una fotografia dei nomi al momento della creazione, non un riferimento vivo: **rinominare gruppo o receiver non riscrive lo slug**, perché cambiarlo spegnerebbe di nascosto ogni script già in produzione. Per riallinearlo c'è `rotate-slug`, che è esplicito e resta ad admin+. Gli slug creati prima della migrazione `0011` (solo token) restano validi e prendono la forma nuova al primo rotate.

> **Sorveglianza dell'attesa (dead man's switch).** Le nove colonne `expected_*`,
> `missing_*` e `last_notification_at` servono a un caso che la catena di severity
> non può coprire: la notifica che **non arriva**. Si dichiara ogni quanto ci si
> aspetta un invio (intervallo fisso oppure espressione cron col suo fuso, mai
> entrambi) e con quale tolleranza; il job `check_expected_schedules` (§11) gira
> ogni 60 secondi e per chi ha sforato scrive una notifica sintetica con
> `severity_source = 'missing'` e la severity configurata, che passa
> dall'instradamento per severity come qualunque altra. Una sola notifica per
> assenza: `missing_alerted_at` la registra e si riarma al primo invio vero, che
> produce anche una notifica `recovered` con severity `info`.
>
> Le notifiche sintetiche non aggiornano `last_notification_at`: se lo facessero,
> l'assenza si riarmerebbe da sola. Receiver `disabled` e tenant `suspended` non
> vengono sorvegliati, perché sarebbero in assenza per definizione.
>
> **Da dove si conta.** Il riferimento è il più recente fra `last_notification_at`
> e `expected_since`: il primo è l'ultimo invio vero, il secondo l'istante in cui
> la sorveglianza è entrata in vigore su questo receiver. La scadenza è la **prima
> occorrenza attesa dopo il riferimento**, più la tolleranza — non la prossima
> occorrenza a partire da adesso. La differenza si vede quando la tolleranza è
> lunga quanto o più del periodo (`0 * * * *` con 2 ore di tolleranza): ancorando
> la scadenza ad adesso resterebbe sempre nel futuro e l'allarme non scatterebbe
> mai. Da qui discende anche che, dopo giorni di silenzio, la data mostrata è la
> prima scadenza saltata — l'istante in cui il guasto è iniziato — e non quella di
> stanotte.
>
> `expected_since` viene riscritto a "adesso" in tre casi, tutti perché il
> silenzio precedente non è un guasto: quando la sorveglianza si accende su un
> receiver che prima non ce l'aveva, quando viene spenta e riaccesa, e quando un
> receiver `disabled` torna `active` (il suo silenzio era voluto — l'ingestion gli
> rispondeva 404). Ogni volta `missing_alerted_at` viene azzerato. Una PATCH che
> non tocca né lo stato né la politica non sposta la finestra, altrimenti
> basterebbe rinominare un receiver per far sparire un allarme in corso.
>
> L'espressione cron viene rifiutata in validazione anche quando è sintatticamente
> valida ma non scatta mai (`0 0 30 2 *`): accettarla vorrebbe dire una
> sorveglianza che non allarmerà mai, cioè il contrario di quanto richiesto. Il
> calcolo avviene nel fuso dichiarato, quindi nei giorni di cambio dell'ora
> l'occorrenza segue l'ora locale (un `0 2 * * *` nel giorno in cui le 2 non
> esistono scivola al primo istante valido).

#### `severity_rules`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| receiver_id | FK → receivers.id | `ON DELETE CASCADE` |
| priority | int | ordine di valutazione crescente, prima corrispondenza vince |
| pattern | text | regex **sintassi RE2**, max 200 caratteri, compilata in validazione |
| case_insensitive | bool | default true (tradotto in flag inline `(?i)`) |
| severity | enum | severity assegnata al match |
| enabled | bool | default true |
| created_at, updated_at | timestamptz | |

```sql
CREATE INDEX ON severity_rules (tenant_id, receiver_id, priority) WHERE enabled;
```

**ReDoS — mitigazione strutturale.** Le regex sono scritte dagli utenti, quindi non vengono eseguite con il modulo `re` di Python: `re` non ha timeout, gira sotto GIL e un pattern con backtracking catastrofico blocca l'intero worker. Si usa **`google-re2`**, che garantisce tempo lineare nella lunghezza dell'input e non può degenerare. Conseguenze da comunicare in UI:

- niente backreference (`\1`) né lookahead/lookbehind (`(?=…)`, `(?<!…)`) — sintassi non supportata da RE2;
- un pattern non compilabile da RE2 viene rifiutato alla creazione con `422` e un messaggio esplicito;
- restano attivi come difesa in profondità il limite di 200 caratteri sul pattern e la valutazione sui soli primi 8KB del contenuto.

#### `notifications`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | generato applicativamente (`uuid4`), non da `gen_random_uuid()`: serve prima del PUT su MinIO |
| tenant_id | FK | |
| receiver_id | FK → receivers.id | `ON DELETE CASCADE` |
| storage_backend | enum(inline, object) | default `inline`. Dove vive il corpo |
| content | text NULL | corpo raw. Valorizzato **solo** se `storage_backend = inline` |
| storage_key | text NULL | chiave dell'oggetto MinIO. Valorizzata **solo** se `storage_backend = object` |
| content_preview | text NOT NULL | primi 4096 caratteri del corpo, sempre presente. Alimenta lista e formatter outbound senza toccare MinIO, ed è la sola parte cercabile dei payload offloaded |
| content_size | int | byte del corpo **originale**, prima di qualunque normalizzazione |
| content_normalized | bool | default false. `true` se il body non era UTF-8 valido o conteneva byte NUL, vedi §6.2 |
| severity | enum(debug…critical) | risolta all'ingestion |
| severity_source | enum(explicit, rule, receiver_default) | tracciabilità: come è stata decisa |
| status | enum(unread, read) | default `unread` |
| verified | bool | default false. flag di verifica manuale dell'operatore; indipendente da status |
| received_at | timestamptz | indexed |
| source_ip | inet NULL | audit / anti-abuso |
| metadata | jsonb | riempito dai moduli di ingestion futuri (mittente email, chat_id Telegram, …). Vuoto per `http_raw` |

> ⚠️ **Nota di implementazione**: `metadata` è un attributo riservato in SQLAlchemy declarative (`Base.metadata`). La colonna si chiama `metadata` a livello SQL ma va mappata con un altro nome Python: `meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)`.

**Vincolo di coerenza**
```sql
ALTER TABLE notifications ADD CONSTRAINT ck_notifications_body CHECK (
  (storage_backend = 'inline' AND content IS NOT NULL AND storage_key IS NULL)
  OR
  (storage_backend = 'object' AND content IS NULL AND storage_key IS NOT NULL)
);
```

**Indici**
```sql
CREATE INDEX ON notifications (tenant_id, received_at DESC, id DESC);              -- paginazione a cursore
CREATE INDEX ON notifications (tenant_id, receiver_id, received_at DESC, id DESC);
CREATE INDEX ON notifications (tenant_id, status) WHERE status = 'unread';
CREATE INDEX ON notifications USING gin ((COALESCE(content, content_preview)) gin_trgm_ops);  -- filtro q
CREATE INDEX ON notifications (storage_key) WHERE storage_backend = 'object';      -- riconciliazione orfani
```
> Il purge è per-tenant e usa il primo indice: nessun indice globale su `received_at`.

### 4.3 Outbound

#### `delivery_channels`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| name | text | etichetta (es. "Slack #alerts-prod") |
| type | enum(slack, google_chat) | |
| webhook_url | bytea | **cifrato a riposo** (AES-GCM con chiave da `NOTIFYHUB_SECRET_KEY`). Mai restituito in chiaro dall'API: si espone solo un hint tipo `https://hooks.slack.com/…/XXXX` |
| enabled | bool | |
| last_success_at, last_error_at, last_error | — | diagnostica in dashboard |
| created_at, updated_at | timestamptz | |

#### `group_channel_bindings`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| group_id | FK | |
| channel_id | FK | unique su `(group_id, channel_id)` |
| min_severity | enum | soglia: si inoltra se `notification.severity >= min_severity`. Default `error` |
| enabled | bool | |
| created_at, updated_at | timestamptz | |

#### `receiver_channel_overrides`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| receiver_id | FK | |
| channel_id | FK | unique su `(receiver_id, channel_id)` |
| mode | enum(override, mute) | `override` = usa `min_severity` di questa riga; `mute` = nessun inoltro verso questo channel |
| min_severity | enum NULL | obbligatorio se `mode = override` |
| created_at, updated_at | timestamptz | |

#### `deliveries` (outbox)
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | |
| notification_id | FK | `ON DELETE CASCADE` |
| channel_id | FK | |
| status | enum(pending, sending, sent, failed, dead) | vedi macchina a stati |
| attempts | int | default 0 |
| next_attempt_at | timestamptz | |
| locked_at | timestamptz NULL | valorizzato entrando in `sending`. Permette al reconciler di riconoscere un worker morto a metà |
| response_code | int NULL | |
| last_error | text NULL | |
| sent_at | timestamptz NULL | |

Unique su `(notification_id, channel_id)` ⇒ idempotenza dell'inoltro.

```sql
CREATE INDEX ON deliveries (status, next_attempt_at) WHERE status IN ('pending', 'failed');
CREATE INDEX ON deliveries (status, locked_at)       WHERE status = 'sending';
CREATE INDEX ON deliveries (tenant_id, channel_id, status);  -- filtri della dashboard
```

**Macchina a stati** — `failed` è uno stato *ritentabile*, non terminale; solo `sent` e `dead` sono finali:
```
pending → sending → sent
                  → failed → (next_attempt_at) → sending → …
                  → dead        (4xx non-429, oppure attempts = 5)
dead → pending    (solo via POST /deliveries/{id}/retry, che azzera attempts, last_error e locked_at)
```

---

### 4.4 Audit

#### `audit_events`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| tenant_id | FK | RLS forzata come ogni tabella di tenant |
| occurred_at | timestamptz | default `now()` |
| actor_user_id | FK users, `ON DELETE SET NULL` | cancellare un utente non cancella la sua storia |
| actor_email, actor_role | text, enum(user_role) | fotografia dell'attore al momento del fatto |
| action | varchar(64) | `notification.marked_verified`, `receiver.updated`, `auth.login_failed`, … |
| resource_type, resource_id | varchar(64), UUID nullable | **nessuna FK**: l'audit vive più a lungo di ciò che descrive |
| resource_label | varchar(255) | etichetta leggibile congelata (nome del receiver, preview della notifica) |
| outcome | enum(success, failure) | `failure` esiste per il solo login rifiutato |
| ip, user_agent, request_id | — | provenienza della richiesta |
| changes | jsonb | `{"campo": {"before": …, "after": …}}` dei soli campi cambiati, segreti mascherati |
| context | jsonb | ciò che non è un diff: filtri e id di un bulk-read, motivo di un login fallito |

Indici: `(tenant_id, occurred_at, id)` per la lista, `(tenant_id, resource_type, resource_id, occurred_at)` per la storia di una risorsa, `(tenant_id, actor_user_id, occurred_at)` e `(tenant_id, action, occurred_at)` per i filtri, più un GIN `jsonb_path_ops` su `(context -> 'notification_ids')` per ritrovare una singola notifica dentro un bulk-read.

Le colonne **denormalizzate** `notifications.read_by/read_at/verified_by/verified_at` rispondono a "chi ha gestito questa notifica" a chiunque veda la notifica; lo **storico** dei passaggi, ripristini compresi, resta qui ed è riservato a owner e admin (§9.6).

---

## 5. Multi-tenancy con Row Level Security

### 5.1 Policy

Ogni tabella con `tenant_id` ha RLS attivo. La GUC va letta **sempre** con il secondo argomento `true` (missing_ok): `current_setting('app.tenant_id')` senza di esso solleva `unrecognized configuration parameter` invece di restituire NULL, facendo esplodere ogni query che gira fuori dal contesto autenticato.

```sql
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON notifications
  USING       (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK  (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

Con GUC non impostata il confronto vale NULL ⇒ zero righe visibili, zero righe scrivibili: il default è il deny.

### 5.2 I tre ruoli Postgres

Nessun ruolo del sistema ha `BYPASSRLS` e nessuno è owner delle tabelle: una query sbagliata non può attraversare i tenant, mai.

| Ruolo | Usato da | Privilegi |
|---|---|---|
| `notifyhub_app` | API autenticata, worker Celery, job per-tenant | CRUD su tutte le tabelle di dominio, sempre sotto `app.tenant_id`. Unica eccezione: su `audit_events` l'`UPDATE` è revocato, la tabella è append-only per l'applicazione |
| `notifyhub_ingest` | Risoluzione dello slug su `/ingest/{slug}` | `SELECT` sulla sola `receivers`, policy dedicata per slug, senza contesto di tenant |
| `notifyhub_auth` | Lookup pre-autenticazione | `SELECT` su `users`, `refresh_tokens`, `invitations`, policy dedicata, senza contesto di tenant |

```sql
-- il ruolo di ingest vede i receiver solo per risolvere lo slug
CREATE POLICY ingest_slug_lookup ON receivers
  FOR SELECT TO notifyhub_ingest USING (true);

-- il ruolo di auth vede le identità solo per il lookup su chiave univoca
CREATE POLICY auth_lookup ON users          FOR SELECT TO notifyhub_auth USING (true);
CREATE POLICY auth_lookup ON refresh_tokens FOR SELECT TO notifyhub_auth USING (true);
CREATE POLICY auth_lookup ON invitations    FOR SELECT TO notifyhub_auth USING (true);
```

I ruoli `notifyhub_ingest` e `notifyhub_auth` hanno **solo `SELECT`**: non possono scrivere nulla. Ogni scrittura passa da `notifyhub_app` con `app.tenant_id` impostato.

### 5.3 Meccanica applicativa

- L'API mantiene **due connection pool distinti**: uno su `notifyhub_app`, uno su `notifyhub_auth`. L'ingestion usa un terzo pool su `notifyhub_ingest`.
- Una dependency FastAPI apre la transazione ed esegue `SET LOCAL app.tenant_id = :tenant_id` prendendo il valore dal claim `tid` del JWT. `SET LOCAL` muore con la transazione ⇒ nessun leak fra richieste sullo stesso pool.
- **Auth (login, refresh, accettazione invito)**: il lookup della riga avviene sul pool `notifyhub_auth`, in sola lettura e su chiave univoca (`email`, `token_hash`). Ricavato il `tenant_id`, tutto il seguito — verifica password, scrittura di `last_login_at`, inserimento del refresh token, creazione dell'utente invitato — avviene in una nuova transazione sul pool `notifyhub_app` con `app.tenant_id` impostato.
- **Ingestion**: la risoluzione slug → receiver avviene sul pool `notifyhub_ingest`; ottenuto il `tenant_id` del receiver, la scrittura della notifica avviene in una nuova transazione sul pool `notifyhub_app`.
- **Worker Celery**: ogni task riceve il `tenant_id` fra i suoi argomenti e lo imposta all'apertura della sessione. I task usano un **engine sincrono** dedicato (§8.4).
- **Job Beat per-tenant** (`purge_notifications`): il job itera i tenant e per ciascuno apre una transazione con `SET LOCAL app.tenant_id`. Costa una query in più a notte e non richiede alcun privilegio speciale.
- **Job Beat cross-tenant** (`cleanup_tokens`, `drain_object_deletions`, `purge_orphan_objects`, `reconcile_deliveries`): operano su tabelle fuori da RLS (`pending_object_deletions`) o iterano anch'essi i tenant. Nessuna eccezione al modello.

Il filtro `tenant_id` resta comunque scritto anche nelle query applicative: RLS è la rete di sicurezza, non l'unica difesa.

---

## 6. Architettura di ingestion

### 6.1 Contratto del modulo

```python
class IngestionResult(BaseModel):
    content: str
    severity: Severity | None = None      # se il canale la dichiara esplicitamente
    metadata: dict[str, Any] = {}

class IngestionModule(Protocol):
    name: str
    async def handle(self, request: IngestRequest) -> IngestionResult: ...
```

I moduli si registrano in un registry (`INGESTION_MODULES: dict[str, IngestionModule]`) e vengono risolti tramite `receivers.ingestion_module`. Il core non conosce il canale: riceve un `IngestionResult` e lo persiste.

### 6.2 Modulo v1 — `http_raw`

- `POST /ingest/{slug}` con corpo testo semplice (`text/plain` o `Content-Type` assente)
- Header opzionale `X-Phase: start|end`: dichiara la fase dell'esecuzione. `start` e' il ping di avvio del wrapper e aggiorna `receivers.last_start_at` **invece** della conclusione; assente o non valido = non dichiarata (invariante I-7)
- Nessun parsing: il body diventa `content`
- Severity esplicita accettata da header `X-Severity` o query param `?severity=`
- Compatibile con:
  ```bash
  curl --data "Backup completato" https://notifyhub.example.com/ingest/{slug}
  curl -H "X-Severity: error" --data "Backup FALLITO" https://.../ingest/{slug}
  wget --post-data="messaggio" https://.../ingest/{slug}
  ```

**Normalizzazione del testo.** Il body arriva come byte grezzi e non c'è garanzia che sia UTF-8: un job che riversa l'output di un tool può produrre byte non decodificabili, e Postgres rifiuta comunque il byte `\x00` in una colonna `text`. L'ingestion **non deve mai fallire per questo**:

1. decodifica `utf-8` con `errors='replace'`;
2. rimozione dei byte NUL;
3. se il passo 1 o 2 ha modificato qualcosa → `content_normalized = true`;
4. `content_size` resta il conteggio dei **byte originali**, non della stringa normalizzata.

In dashboard le notifiche con `content_normalized = true` mostrano un badge "contenuto normalizzato". Per i payload offloaded l'oggetto su MinIO conserva i byte originali: il download restituisce l'originale, mentre `content_preview` e la ricerca lavorano sulla versione normalizzata.

### 6.3 Idempotenza — `X-Request-Id`

Un cron che va in timeout di rete ritenta, e senza deduplica genera notifiche doppie. Header **opzionale**:

- chiave Redis `ingest:idem:{receiver_id}:{sha256(X-Request-Id)}`, scritta con `SET … NX EX 300` (finestra di 5 minuti);
- **prima occorrenza** → ingestion normale, risposta `201`, nel valore della chiave si memorizza l'id della notifica creata;
- **occorrenza ripetuta entro la finestra** → nessuna scrittura, risposta **`200`** con lo stesso corpo della `201` originale (`{"id": …, "severity": …, "forwarded_to": …}`) e header `Idempotent-Replay: true`;
- header assente → nessuna deduplica, comportamento identico a oggi.

La finestra di 5 minuti copre il retry di rete senza impedire l'invio legittimo dello stesso messaggio più tardi (un check di backup che gira ogni ora manda la stessa riga, e va salvata ogni volta).

### 6.4 Moduli previsti (non in v1)

`email_inbound`, `telegram_bot`, `webhook_json` (GitHub, Grafana, Alertmanager), `mqtt`.

### 6.5 Storage del payload — inline vs object store

Il corpo di una notifica può arrivare a 20MB. Tenere multi-MB in una colonna `text` significa TOAST, backup gonfi, `pg_dump` lenti e purge costosi. Soglia unica di sistema:

| Parametro | Valore | Note |
|---|---|---|
| `INLINE_MAX_BYTES` | 1.048.576 (1MB) | env var. Corpi `<=` soglia restano in colonna `content` |
| Oltre soglia | MinIO | `storage_backend = 'object'`, `content = NULL`, `storage_key` valorizzata |

**Chiave dell'oggetto**

```
{bucket}/{tenant_id}/{yyyy}/{mm}/{dd}/{notification_id}.txt
```

Bucket unico per deployment (`notifyhub-payloads`, env `NOTIFYHUB_S3_BUCKET`), prefisso per tenant: il prefisso rende banale sia il purge per tenant sia una eventuale lifecycle policy, senza moltiplicare i bucket. Versioning disattivato, accesso solo server-side da `api` e `worker` — **nessuna presigned URL esposta al browser in v1**: il download passa dall'API, che applica ruolo e RLS.

**Flusso di scrittura (ingestion)**

1. Il body viene letto in streaming in un buffer *spooled* (in RAM fino a 1MB, poi file temporaneo), contando i byte e interrompendo appena si supera `receivers.max_body_bytes` → `413`.
2. Normalizzazione del testo (§6.2) e calcolo di `content_preview` = primi 4096 caratteri. Le `severity_rules` si valutano sui primi 8KB dello stesso buffer: **nessun accesso a MinIO nella catena di severity**.
3. Se `size <= INLINE_MAX_BYTES` → `content` in colonna, fine.
4. Altrimenti: `PUT` su MinIO **prima** del commit Postgres. PUT fallito → `503`, nessuna riga scritta. PUT riuscito con commit fallito → oggetto orfano, recuperato dal job `purge_orphan_objects`.
5. L'`id` della notifica è generato applicativamente prima del PUT, perché entra nella chiave dell'oggetto.

**Flusso di lettura**

- `GET /api/v1/notifications` → solo `content_preview` troncato a 500 caratteri + `content_size`. Mai MinIO.
- `GET /api/v1/notifications/{id}` → se `inline` restituisce `content`; se `object` restituisce i metadati + `content_url`.
- `GET /api/v1/notifications/{id}/content` → streaming proxy dell'oggetto, `Content-Type: text/plain`, `Content-Length` **dei byte effettivamente inviati**. Non è `content_size`: quella è la dimensione del corpo *originale*, e per un payload `inline` normalizzato (UTF-8 non valido sostituito, byte NUL rimossi — §6.2) le due misure differiscono. Dichiarare `content_size` fa troncare la risposta.
- Il **worker outbound non legge mai MinIO**: formatta da `content_preview` (4096 caratteri, sopra i 3800 richiesti da Google Chat).

**Cancellazione**

Ogni percorso che elimina notifiche (`DELETE` singola, purge per retention, cascade da receiver/group/tenant) deve rimuovere anche gli oggetti, e il `CASCADE` di Postgres non lo fa. Un trigger `AFTER DELETE` accoda la chiave in `pending_object_deletions`, drenata da un job Beat. L'ordine è deliberato: cancellare prima l'oggetto e poi la riga renderebbe la notifica irrecuperabile se la transazione va in rollback.

#### `pending_object_deletions`
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | |
| storage_key | text | nessun `tenant_id`: tabella fuori da RLS, scritta da trigger |
| enqueued_at | timestamptz | |
| attempts | int | default 0 |

---

## 7. Risoluzione della severity

Catena di precedenza, **prima corrispondenza vince**:

```
1. ESPLICITA      header X-Severity  oppure  query param ?severity=
                  ↓ (assente o valore non valido)
2. REGOLE REGEX   severity_rules del receiver, ordinate per priority crescente,
                  valutate con RE2 sui primi 8KB del contenuto, prima match vince
                  ↓ (nessun match)
3. DEFAULT        receivers.default_severity
```

Il campo `notifications.severity_source` registra quale anello ha deciso — serve a debuggare "perché questa notifica non è stata inoltrata".

Una severity esplicita non valida (es. `X-Severity: banana`) **non** fa fallire l'ingestion: viene ignorata, si scende al passo 2 e l'evento finisce nei log applicativi.

**Ordinamento.** La severity è un enum Postgres dichiarato in ordine crescente:

```sql
CREATE TYPE severity AS ENUM ('debug', 'info', 'warning', 'error', 'critical');
```

Gli enum di Postgres si confrontano nativamente secondo l'ordine di dichiarazione, quindi `severity >= 'error'::severity` funziona ed è indicizzabile senza alcuna funzione di mapping. La corrispondenza numerica (`debug=10 … critical=50`) resta **solo** come costante Python per ordinamenti e badge in UI: non esiste una funzione SQL di conversione, che sarebbe ridondante e — se non dichiarata `IMMUTABLE` — renderebbe gli indici inutilizzabili.

---

## 8. Flusso di inoltro (outbound)

### 8.1 Risoluzione delle destinazioni

Per una notifica su receiver R nel gruppo G:

```
candidati = tutti i GroupChannelBinding di G con enabled = true
per ogni candidato C:
    override = ReceiverChannelOverride(R, C.channel)
    se override.mode == 'mute'      → scarta
    se override.mode == 'override'  → soglia = override.min_severity
    altrimenti                      → soglia = C.min_severity
    se notification.severity >= soglia AND channel.enabled → crea Delivery(pending)
```

### 8.2 Pattern outbox + worker

1. L'endpoint di ingestion, **nella stessa transazione** in cui salva la `Notification`, calcola le destinazioni e inserisce le righe `deliveries` in stato `pending`. Nessun invio sincrono: la risposta HTTP al mittente non aspetta Slack.
2. Il task Celery viene accodato **dopo il commit**, mai dentro la transazione (§8.3).
3. Un worker preleva la delivery, la marca `sending` valorizzando `locked_at`, fa il POST al webhook.
4. Esito:
   - `2xx` → `sent`, `sent_at` valorizzato
   - `429` → rispetta `Retry-After`, ripianifica
   - `5xx` o timeout → `failed`, retry con backoff esponenziale + jitter: 30s, 2m, 10m, 1h, 6h (5 tentativi)
   - `4xx` diverso da 429 (webhook revocato) → `dead` immediato, `delivery_channels.last_error` aggiornato e channel segnalato in dashboard
5. Esauriti i tentativi → `dead`. Nessuna perdita silenziosa: le delivery morte sono elencabili e ri-schedulabili dalla UI.

`reconcile_deliveries` (ogni 5 minuti) ripesca:
- le delivery in `pending`/`failed` con `next_attempt_at` scaduto — copre il broker che perde un messaggio;
- le delivery in `sending` con `locked_at` più vecchio di 10 minuti — copre il worker ucciso a metà lavoro.

### 8.3 Accodamento dopo il commit

Chiamare `dispatch_delivery.delay()` dentro la transazione è la fonte di bug più comune di questo pattern: il worker è veloce, prende il task e cerca una riga che nessuno ha ancora committato. L'enqueue viene registrato su un hook di sessione:

```python
@event.listens_for(session.sync_session, "after_commit")
def _enqueue(_):
    for delivery_id, tenant_id in pending_dispatch:
        dispatch_delivery.delay(str(delivery_id), str(tenant_id))
```

Se il processo muore fra commit ed enqueue il task si perde, e la riga resta `pending`: la ripesca `reconcile_deliveries` entro 5 minuti. L'hook è l'ottimizzazione di latenza, il reconciler è la garanzia di consegna.

### 8.4 Worker Celery e sessione sincrona

L'API usa SQLAlchemy in modalità async, Celery è un runtime sincrono. Aprire un event loop per ogni task (`asyncio.run(...)`) è costoso e lascia connessioni appese. La scelta è tenere **due sessionmaker sugli stessi modelli dichiarativi**:

| Processo | Engine | Sessione |
|---|---|---|
| `api` | `create_async_engine` | `AsyncSession` |
| `worker`, `beat` | `create_engine` | `Session` |

I modelli, gli enum e la logica di dominio sono condivisi; si duplica solo il sottile strato di accesso usato dai task, che è piccolo (leggi delivery, POST, aggiorna riga).

### 8.5 Formattazione dei messaggi

Il contenuto di una notifica può arrivare a 20MB, i canali no:

| Canale | Limite pratico | Strategia |
|---|---|---|
| Slack | ~3000 caratteri per blocco `section` | Block Kit: header con severity + nome receiver, sezione con i primi ~2800 caratteri, footer con link alla notifica in dashboard |
| Google Chat | ~4096 caratteri per messaggio | `cardV2` con titolo, testo troncato a ~3800 caratteri, bottone "Apri in NotifyHub" |

Il troncamento è sempre segnalato (`… [troncato, N KB totali]`, con `N` da `content_size`). Il messaggio inoltrato è una **sintesi con link**, il dettaglio completo vive in NotifyHub. La sorgente del testo è sempre `content_preview`: il worker non tocca né il TOAST né MinIO.

Codifica colore per severity: `critical`/`error` rosso, `warning` giallo, `info`/`debug` grigio.

---

## 9. API

Prefisso management: `/api/v1`. Tutte le risposte di errore seguono RFC 7807 (`application/problem+json`).

### 9.1 Ingestion (pubblica, protetta dallo slug)

| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/ingest/{slug}` | Crea una Notification. Body = testo semplice |

Header/param opzionali: `X-Severity`, `?severity=`, `X-Request-Id` (idempotenza, §6.3).

**Codici di risposta**

| Codice | Quando |
|---|---|
| 200 | Replay idempotente: `X-Request-Id` già visto negli ultimi 5 minuti. Header `Idempotent-Replay: true` |
| 201 | Notifica creata. Body: `{"id": "...", "severity": "error", "forwarded_to": 2}` |
| **404** | Slug inesistente **oppure** receiver `disabled` **oppure** tenant `suspended` — corpo e timing identici |
| 413 | Body oltre `receivers.max_body_bytes` |
| 415 | `Content-Type` non supportato dal modulo |
| 429 | Rate limit o quota giornaliera superati. Header `Retry-After` |
| 503 | Object store non raggiungibile su un payload offloaded |

**Perché non esiste il 410.** Lo slug è l'unica credenziale dell'endpoint di ingestion. Rispondere `410` su un receiver disabilitato confermerebbe a chiunque abbia una lista di slug quali sono validi, trasformando il `disabled` in un oracolo di enumerazione. Il receiver disabilitato risponde `404` esattamente come uno slug inesistente.

Il bisogno diagnostico dell'amministratore è coperto altrove: ogni tentativo verso un receiver `disabled` incrementa un contatore Redis `ingest:rejected:{receiver_id}` con TTL 24h, e la dashboard mostra sul receiver un avviso *"disabilitato — 37 invii rifiutati nelle ultime 24 ore"*. Chi ha accesso legittimo vede tutto; chi ha solo lo slug non distingue nulla.

### 9.2 Auth

| Metodo | Path | Descrizione |
|---|---|---|
| POST | `/api/v1/auth/register` | Crea Tenant + primo utente `owner`. **Disabilitato di default** (§10.2) |
| POST | `/api/v1/auth/login` | email + password → access token (15 min) + refresh token (30 gg) |
| POST | `/api/v1/auth/refresh` | Rotazione del refresh token |
| POST | `/api/v1/auth/logout` | Revoca la famiglia di refresh token |
| GET | `/api/v1/auth/me` | Profilo + tenant + ruolo |
| POST | `/api/v1/invitations` | Invita un utente (admin+). Risposta: `{"invite_url": "...", "email_sent": true|false}` |
| POST | `/api/v1/invitations/accept` | Accetta invito. **Token nel body**, mai nel path |
| GET | `/api/v1/users` | Lista membri (admin+) |
| PATCH/DELETE | `/api/v1/users/{id}` | Cambio ruolo / rimozione (admin+). `409` se tocca l'ultimo owner |

Claim del JWT: `sub` (user_id), `tid` (tenant_id), `role`, `exp`, `jti`.

Il token di invito viaggia nel corpo della richiesta e non nel path: un URL con dentro un segreto finisce nell'access log di nginx, nell'header `Referer` e nella cronologia del browser, il che contraddirebbe la scelta di persisterlo solo come hash. Il link inviato all'utente è `https://host/invite#token=…` — il frammento non viene mai trasmesso al server — e la SPA lo gira nel body della POST.

### 9.3 Management

| Metodo | Path | Descrizione |
|---|---|---|
| GET/POST | `/api/v1/groups` | Lista / crea gruppo |
| GET/PATCH | `/api/v1/groups/{id}` | Dettaglio, rinomina |
| GET | `/api/v1/groups/{id}/delete-impact` | Preflight: `{"receivers": 4, "notifications": 18402, "deliveries": 2210}` |
| DELETE | `/api/v1/groups/{id}` | Elimina in cascata. Richiede `?confirm={nome esatto del gruppo}` |
| GET/POST | `/api/v1/groups/{id}/receivers` | Lista / crea receiver (genera lo slug) |
| GET/PATCH/DELETE | `/api/v1/receivers/{id}` | Dettaglio, rinomina/abilita/limiti, elimina |
| POST | `/api/v1/receivers/{id}/rotate-slug` | Rigenera lo slug (admin+, invalida gli script esistenti). Nuovo token, prefisso ricostruito sui nomi attuali |
| GET | `/api/v1/receivers/{id}/wrapper-script` | `scripts/notifyhub-run.sh` precompilato con URL pubblica e slug, `text/x-shellscript` + `Content-Disposition: attachment` |
| GET/POST | `/api/v1/receivers/{id}/severity-rules` | Lista / crea regola |
| PATCH/DELETE | `/api/v1/severity-rules/{id}` | Modifica / elimina regola |
| POST | `/api/v1/receivers/{id}/test-severity` | Dato un testo di prova, restituisce la severity risolta e quale regola ha vinto |
| GET/PATCH | `/api/v1/tenant` | Impostazioni del tenant (owner). `409` se il nuovo `max_body_bytes` è sotto quello di receiver esistenti |

**Cancellazione di un gruppo non vuoto** — cascade su receiver, notifiche, delivery e oggetti MinIO, con conferma esplicita. La UI chiama prima `delete-impact`, mostra i conteggi reali (*"verranno eliminati 4 receiver e 18.402 notifiche"*) e chiede di digitare il nome del gruppo; l'API rifiuta con `422` se `confirm` non corrisponde. Il blocco "svuota prima" è stato scartato: costringe a cancellare a mano decine di receiver per dismettere un ambiente.

**Abbassamento del cap del tenant** — se il nuovo `tenants.max_body_bytes` è inferiore al `max_body_bytes` di uno o più receiver, il `PATCH` risponde `409` con l'elenco dei receiver in conflitto. Nessun adeguamento silenzioso: modificare in automatico la configurazione di dieci receiver è il tipo di cambiamento che si scopre tre settimane dopo.

### 9.4 Canali e inoltro

| Metodo | Path | Descrizione |
|---|---|---|
| GET/POST | `/api/v1/channels` | Lista / crea DeliveryChannel |
| PATCH/DELETE | `/api/v1/channels/{id}` | Modifica / elimina |
| POST | `/api/v1/channels/{id}/test` | Invia un messaggio di prova al webhook |
| GET/POST | `/api/v1/groups/{id}/channels` | Lista / crea binding gruppo → channel |
| PUT/DELETE | `/api/v1/groups/{id}/channels/{channel_id}` | Modifica `min_severity` / rimuove il binding |
| GET/POST | `/api/v1/receivers/{id}/channels` | Lista / crea override o mute |
| PUT/DELETE | `/api/v1/receivers/{id}/channels/{channel_id}` | Modifica / rimuove l'override |
| GET | `/api/v1/deliveries?status=&channel_id=` | Storico inoltri, per diagnosticare i fallimenti |
| POST | `/api/v1/deliveries/{id}/retry` | Ri-accoda una delivery `dead` |

Le sotto-risorse sono identificate da `channel_id`: `PUT`/`DELETE` su una collezione, senza dire su quale binding agiscono, non sono indirizzabili.

### 9.5 Consumption

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/notifications` | Filtri: `group_id`, `receiver_id`, `status`, `verified`, `severity_min`, `source`, `q` (full-text), `from`, `to`. `status` (letta/non letta) e `verified` (revisione manuale) sono **due dimensioni indipendenti** e si combinano. Paginazione **a cursore** su `(received_at, id)` |
| GET | `/api/v1/notifications/{id}` | Dettaglio. `content` inline se ≤1MB, altrimenti `content_url` |
| GET | `/api/v1/notifications/{id}/content` | Streaming del corpo completo (proxy MinIO se offloaded) |
| PATCH | `/api/v1/notifications/{id}` | Segna letta / non letta e verificata / non verificata. Body: almeno uno fra `status` e `verified`; body vuoto → 422. Registra chi ha gestito la notifica (`read_by`/`read_at`, `verified_by`/`verified_at`, esposti come `read_by_email`/`verified_by_email`) e lascia un evento di audit (§9.6) |
| POST | `/api/v1/notifications/bulk-read` | Segna in blocco (per filtro, gli stessi della lista). Un solo evento di audit per l'intera operazione, con filtri, conteggio e id delle notifiche toccate |
| DELETE | `/api/v1/notifications/{id}` | Elimina |
| GET | `/api/v1/stats/summary` | Conteggi per severity / non lette e albero gruppo → receiver (`by_group[].receivers[]`, con `total` e `unread_count` per receiver, compresi quelli a zero), per la home della dashboard |

La lista **non** restituisce il `content` completo ma i primi 500 caratteri di `content_preview` + `content_size`.

Dentro un gruppo la dashboard consuma questa lista **un receiver alla volta** (`receiver_id`), una tabella per receiver del gruppo, ciascuna col proprio cursore: con un cursore unico di gruppo un receiver molto attivo riempirebbe la pagina e gli altri resterebbero vuoti pur avendo notifiche piu' vecchie. Nella tabella il contenuto non viene stampato: la cella porta un link *Apri* al dettaglio. `content_preview` resta comunque nella risposta, perche' e' parte del contratto dell'API e non un dettaglio della dashboard.

Il filtro `q` è una **ricerca per sottostringa case-insensitive su `COALESCE(content, content_preview)`**, servita da un indice GIN `pg_trgm` sulla stessa espressione:

- **payload inline** (≤ `NOTIFYHUB_INLINE_MAX_BYTES`, default 1MB): la ricerca copre il **contenuto intero**;
- **payload offloaded su MinIO**: `content` è NULL per vincolo, quindi la ricerca ricade sui 4096 caratteri di `content_preview`. La UI lo dichiara accanto al campo di ricerca.

I metacaratteri LIKE (`%`, `_`, `\`) digitati dall'utente sono neutralizzati: cercare `50%` cerca il testo `50%`, non un jolly. La semantica è per sottostringa e non per parola intera (`err` trova `error`), a differenza del `plainto_tsquery` usato fino alla migrazione 0014.

*v2: `GET /api/v1/notifications/stream` (SSE) alimentato da Redis pub/sub.*

---

### 9.6 Audit

Registro di **chi ha fatto cosa**, riservato a **owner e admin** (`require_admin`): un member o un viewer riceve 403 anche sui propri eventi. Cio' che serve a lavorare — chi ha letto o verificato una notifica — sta invece sulla notifica stessa ed e' visibile a chiunque la veda.

| Metodo | Path | Descrizione |
|---|---|---|
| GET | `/api/v1/audit/events` | Tutti gli eventi. Filtri: `actor_user_id`, `action`, `resource_type`, `resource_id`, `outcome`, `from`, `to`. Paginazione a cursore su `(occurred_at, id)` DESC |
| GET | `/api/v1/audit/notification-status` | Vista filtrata sulle sole letture e verifiche. Filtro `notification_id`: trova sia la PATCH singola (`resource_id`) sia i bulk-read, che portano gli id dentro `context` |
| GET | `/api/v1/audit/export` | Gli stessi filtri, in CSV (`format=csv`, default) o JSON. Oltre 50.000 righe risponde 422: l'export e' un file da scaricare adesso, non un dump storico |

Come nasce un evento:

- **per costruzione**, da un hook `before_flush` di SQLAlchemy: ogni INSERT/UPDATE/DELETE passato dall'ORM durante una richiesta autenticata diventa un evento, con il diff dei soli campi cambiati. Un endpoint nuovo e' tracciato senza scrivere una riga nel router;
- **esplicitamente**, per i fatti che l'ORM non vede: login riuscito, login fallito, logout, `bulk-read` (una sola UPDATE per N notifiche).

Invarianti:

- **Stessa transazione del fatto**. Se l'audit non si scrive, la modifica non si scrive.
- **Nessun attore umano, nessun evento**. L'ingestion e i job Celery non ne producono: la notifica e' gia il proprio registro, e un secondo giornale del traffico di macchina non serve a nessuno.
- **Segreti mascherati**. `webhook_url`, `password_hash`, `token_hash` e i corpi delle notifiche non finiscono nel diff: al loro posto `[redacted]`.
- **Righe autosufficienti**. `actor_email`, `actor_role` e `resource_label` sono fotografie del momento del fatto; `actor_user_id` va a NULL se l'utente viene cancellato, e `resource_id` non ha alcuna FK verso `notifications`, che vivono meno dell'audit.
- **Append-only per l'applicazione**: `REVOKE UPDATE ON audit_events FROM notifyhub_app` (migrazione 0016). Il `DELETE` resta per la sola purge di ritenzione.
- **Login falliti**: registrati quando l'email corrisponde a un utente esistente. Con un'email sconosciuta non esiste il tenant a cui attribuire la riga (RLS): quel caso resta nei log strutturati.
- **Richieste rifiutate** (403/422): nessun evento. Nulla e' cambiato, e il rifiuto sta nei log. Fa eccezione il login fallito, che e' il segnale di sicurezza per cui l'audit esiste.

---

## 10. Sicurezza

### 10.1 Endpoint di ingestion

- **Slug a 22 caratteri** (`secrets.token_urlsafe(16)`, 128 bit) — enumerazione non praticabile
- **Rate limiting su Redis**, doppio contatore sliding window:
  - per slug: `receivers.rate_limit_per_min` (default 60/min). **Il valore `0` disattiva il solo limite per-slug**, non quello per IP
  - per IP sorgente: 300/min aggregati su tutti gli slug, per contenere gli scan
- **Il contatore per IP è il primo gate**, valutato prima della risoluzione dello slug: uno scan di slug inesistenti non deve generare query
- **Limite di dimensione a due livelli**: il body è letto in streaming e interrotto appena supera `receivers.max_body_bytes`; a monte, nginx `client_max_body_size` è impostato all'hard limit di sistema (20MB). Su `location /ingest/` serve `proxy_request_buffering off`, altrimenti nginx accumula i 20MB su disco prima di inoltrarli e il limite per-receiver non interrompe più nulla in anticipo
- **404 uniforme** per slug inesistente, receiver disabilitato e tenant sospeso, con corpo e tempi di risposta indistinguibili
- `source_ip` prelevato da `X-Forwarded-For` **solo** se il proxy è in una lista di trusted proxy configurata

### 10.2 Management

- Password con Argon2id, policy minima 12 caratteri
- **Rate limit del login su `(email, IP)`**, 10 tentativi / 15 min. L'IP si risolve con la stessa regola dell'ingestion (§10.1: `X-Forwarded-For` solo da un trusted proxy): dietro reverse proxy l'IP della connessione è quello del proxy per *tutti*, e senza questa risoluzione la chiave si riduce alla sola email — 10 tentativi sbagliati basterebbero a bloccare un account noto a tutti gli altri
- **Scritture sulle notifiche riservate a `member` e superiori**: `PATCH /notifications/{id}`, `POST /notifications/bulk-read` e `DELETE /notifications/{id}` richiedono il ruolo `member`; un `viewer` legge e riceve `403` su ognuna
- **Registrazione pubblica disabilitata di default**: `ALLOW_PUBLIC_REGISTRATION=false`. Con il flag a `false`, `POST /auth/register` risponde `403` e il primo tenant si crea da CLI:
  ```bash
  docker compose run --rm api python -m notifyhub.cli bootstrap \
      --tenant-name "ACME" --email admin@acme.it
  ```
  Un'istanza self-hosted esposta su internet con la registrazione aperta si riempie di tenant spazzatura; chi vuole il comportamento SaaS alza il flag.
- Access token 15 minuti, refresh token rotante con rilevamento del riuso (revoca dell'intera famiglia)
- ⚠️ Il logout revoca la famiglia di refresh token ma **non** invalida l'access token già emesso, che resta valido al massimo 15 minuti. È una scelta consapevole per l'MVP: una denylist dei `jti` su Redis si aggiunge in un'ora se il modello di minaccia lo richiede, e non cambia nulla nella struttura
- Rate limit sul login: 10 tentativi / 15 min per `(email, IP)`
- CORS ristretto all'origin del frontend, configurabile
- Autorizzazione verificata a livello di dependency per ogni endpoint, oltre a RLS

### 10.3 Segreti

- `webhook_url` dei channel cifrato con AES-GCM, chiave da variabile d'ambiente `NOTIFYHUB_SECRET_KEY`
- I webhook URL non compaiono mai nei log né nelle risposte API (solo un hint mascherato)
- Token di invito persistiti solo come hash SHA-256 e trasmessi solo nel body, mai in un URL path

### 10.4 Superficie esposta

`nginx` instrada verso l'esterno **solo** `/`, `/api/v1/*`, `/ingest/*`, `/healthz`, `/readyz`. Restano su porte interne, non pubblicate:

| Endpoint | Porta | Motivo |
|---|---|---|
| `/metrics` (Prometheus) | 9100 sul container `api` | Espone volumi, latenze e nomi di tenant: è telemetria interna, non un endpoint pubblico da proteggere con un token statico |
| Console MinIO | 9001 | Amministrazione dello storage |

---

## 11. Retention e manutenzione

Job Celery Beat. Tutti girano con il ruolo `notifyhub_app`, senza alcun privilegio di bypass: quelli che toccano dati di tenant iterano i tenant e impostano `app.tenant_id` per ciascuno.

| Job | Frequenza | Azione |
|---|---|---|
| `purge_notifications` | ogni notte 03:00 | Per ogni tenant con `retention_days` non NULL, elimina le notifiche più vecchie. A batch di 10.000 righe per non bloccare la tabella |
| `purge_audit_events` | ogni notte 05:00 | Per ogni tenant con `audit_retention_days` non NULL (default 365), elimina gli eventi di audit più vecchi, a batch di 10.000 righe. Ritenzione separata da quella delle notifiche, che di default è 90 giorni: l'audit deve sopravvivere a ciò che descrive. Non usa `SELECT … FOR UPDATE SKIP LOCKED` come le altre purge, perché bloccare una riga richiederebbe il privilegio di UPDATE, revocato apposta su questa tabella |
| `purge_deliveries` | ogni notte 03:30 | Elimina le delivery `sent` più vecchie di 30 giorni; le `dead` restano finché non archiviate manualmente |
| `cleanup_tokens` | ogni ora | Elimina refresh token scaduti/revocati e inviti scaduti |
| `reconcile_deliveries` | ogni 5 min | Ripesca le delivery `pending`/`failed` con `next_attempt_at` scaduto e le `sending` con `locked_at` più vecchio di 10 minuti |
| `drain_object_deletions` | ogni 10 min | Svuota `pending_object_deletions` cancellando gli oggetti da MinIO. Dopo 10 tentativi falliti la riga resta e alimenta una metrica di allarme |
| `purge_orphan_objects` | ogni notte 04:00 | Elimina gli oggetti del bucket più vecchi di 24h senza riga corrispondente in `notifications.storage_key`. Recupera i PUT riusciti con commit fallito. ⚠️ Le `storage_key` note vanno raccolte **iterando i tenant** con `SET LOCAL app.tenant_id`: `notifications` ha `FORCE ROW LEVEL SECURITY` e una lettura senza contesto di tenant torna zero righe *senza errore*, facendo risultare orfano ogni oggetto |
| `recompute_tenant_usage` | ogni notte 04:30 | Ricalcola lo spazio occupato per tenant (F7, alimenta `max_storage_bytes`) |
| `check_expected_schedules` | ogni 60 s | **Sorveglianza dell'attesa** (§4.2, `receivers.expected_*`): per ogni tenant attivo confronta `last_notification_at` con la scadenza dichiarata (intervallo o cron + tolleranza) e scrive una notifica sintetica `severity_source = 'missing'` per chi ha sforato, una `recovered` (`info`) per chi e' tornato a inviare. Una sola notifica per assenza, riarmata al primo invio vero |

⚠️ *Partitioning mensile di `notifications` su `received_at`: rimandato a fase 2. Attenzione, quando si farà: il trigger `AFTER DELETE` per gli oggetti non scatta su `DROP PARTITION` — serve una passata esplicita che accodi le `storage_key` della partizione prima del drop.*

---

## 12. Flusso end-to-end

1. L'operatore crea il tenant "ACME" da CLI (`bootstrap`) e riceve le credenziali del primo `owner`
2. L'owner crea il Group "Server Produzione" e il Receiver "Backup notturno" → slug `Kj8mQ2xN7vB4pR9wLs3tYc`
3. Configura un DeliveryChannel "Slack #ops" (webhook incollato) e lo lega al gruppo con `min_severity = error`
4. Sul receiver aggiunge una SeverityRule: pattern `FALL(ITO|IMENT)|ERROR|CRITICAL` → `error` (compilato con RE2 in validazione)
5. Il cron notturno sul server esegue:
   ```bash
   curl -H "X-Request-Id: backup-2026-08-01" \
        --data "Backup FALLITO: disco pieno su /var" \
        https://notifyhub.example.com/ingest/Kj8mQ2xN7vB4pR9wLs3tYc
   ```
6. Il modulo `http_raw` applica in ordine: rate limit per IP, risoluzione dello slug, rate limit per slug, controllo di dimensione, deduplica su `X-Request-Id`, normalizzazione del testo
7. Severity risolta a `error` (fonte: `rule`). Corpo sotto 1MB → resta inline. Notification e Delivery `pending` verso "Slack #ops" salvate nella **stessa transazione**
8. Al commit l'hook accoda `dispatch_delivery`; risposta `201` al cron in pochi millisecondi, senza attendere Slack
9. Il worker consuma la delivery e posta su Slack un blocco rosso con il testo e il link alla notifica
10. Se il cron va in timeout e ritenta entro 5 minuti con lo stesso `X-Request-Id`, riceve `200` con l'id della notifica già creata: nessun doppione, nessun secondo messaggio su Slack
11. L'utente apre la dashboard, filtra per gruppo, legge il dettaglio e la marca come letta

---

## 13. Deploy

`docker-compose.yml` con i servizi:

| Servizio | Ruolo |
|---|---|
| `nginx` | Reverse proxy, TLS, `client_max_body_size`, `proxy_request_buffering off` su `/ingest/`, serve la SPA buildata |
| `api` | FastAPI su uvicorn/gunicorn. Porta 8000 pubblica, 9100 interna per `/metrics` |
| `worker` | Celery worker (coda `delivery`), engine SQLAlchemy sincrono |
| `beat` | Celery Beat (purge, riconciliazione, manutenzione oggetti) |
| `postgres` | PostgreSQL 16 con volume persistente |
| `redis` | Broker Celery + rate limiting + idempotenza + (v2) pub/sub SSE |
| `minio` | Object store S3-compatible per i payload > 1MB. Volume persistente, console non esposta da nginx |
| `minio-init` | One-shot: crea il bucket `notifyhub-payloads`, policy `private`, utente di servizio limitato al bucket |
| `migrate` | One-shot: migrazioni Alembic + creazione dei tre ruoli Postgres e delle policy RLS, prima dell'avvio di `api` |

**Env var principali**

```
NOTIFYHUB_SECRET_KEY            # AES-GCM per i webhook
DATABASE_URL_APP                # notifyhub_app
DATABASE_URL_AUTH               # notifyhub_auth  (sola lettura su users/refresh_tokens/invitations)
DATABASE_URL_INGEST             # notifyhub_ingest (sola lettura su receivers)
NOTIFYHUB_S3_ENDPOINT / _BUCKET / _ACCESS_KEY / _SECRET_KEY / _REGION
NOTIFYHUB_INLINE_MAX_BYTES=1048576
ALLOW_PUBLIC_REGISTRATION=false
SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM   # opzionali
```

**SMTP opzionale.** `POST /invitations` genera sempre un `invite_url` restituito nella risposta e mostrato nella UI con un bottone "copia link". Se le variabili SMTP sono configurate viene anche inviata la mail e la risposta riporta `email_sent: true`; altrimenti `false` e l'admin distribuisce il link come preferisce. Nessuna dipendenza bloccante nel deploy.

**Client object store**: `aioboto3`/`aiobotocore` sull'`api` (async), `boto3` su `worker` e `beat` (sync). MinIO è S3-compatible: lo stesso codice punta a S3 o GCS reali se un domani si esce dal self-hosted.

Healthcheck: `GET /healthz` (liveness) e `GET /readyz` (Postgres + Redis + MinIO `HeadBucket`).
Osservabilità: log strutturati JSON con `request_id` e `tenant_id`; metriche Prometheus su porta interna con contatori di ingestion, delivery per esito, latenze e code di manutenzione.

---

## 14. Roadmap di sviluppo

| Fase | Contenuto |
|---|---|
| **F1 — Fondamenta** | Scaffolding FastAPI, Postgres + Alembic, modello dati completo (incluse le colonne di quota), **tre ruoli Postgres + policy RLS con `current_setting(…, true)`**, trigger `updated_at`, trigger di cancellazione oggetti, docker-compose con MinIO |
| **F2 — Auth** | CLI `bootstrap`, registrazione gated dal flag, login su email globale con pool `notifyhub_auth`, JWT + refresh rotante, matrice ruoli, vincolo ultimo owner, inviti con link copiabile e SMTP opzionale |
| **F3 — Core dominio** | CRUD Group/Receiver, generazione e rotazione slug, CRUD severity-rules con validazione RE2, `delete-impact` + cancellazione confermata, `PATCH /tenant` con controllo dei cap |
| **F4 — Ingestion** | Endpoint `/ingest/{slug}`, modulo `http_raw`, normalizzazione UTF-8, limiti di dimensione, **offload su MinIO oltre 1MB**, rate limiting a due livelli, idempotenza `X-Request-Id`, catena di severity |
| **F5 — Outbound** | DeliveryChannel, binding e override, outbox, hook `after_commit`, worker Celery sincrono, formatter Slack e Google Chat, retry e macchina a stati |
| **F6 — Dashboard** | SPA React: liste, filtri, dettaglio con download dei payload offloaded, gestione gruppi/receiver/canali, diagnostica delivery, badge "normalizzato" e "N invii rifiutati" |
| **F7 — Manutenzione** | Purge, riconciliazione, drain e orphan objects, **enforcement delle quote per tenant**, metriche, healthcheck |
| **F8 — v2** | SSE real-time, moduli di ingestion aggiuntivi, digest schedulati, partitioning, eventuale denylist dei `jti` |

---

## 15. Decisioni prese

**Dominio e dati**
- ✅ Un Group contiene più Receiver (1:N)
- ✅ Ingestion v1: solo testo semplice nel body, normalizzato in UTF-8 senza mai fallire
- ✅ Payload oltre 1MB su **MinIO**, in tabella `storage_key` + `content_preview` da 4096 caratteri (unica parte cercabile di quelle righe)
- ✅ Severity da header/param espliciti → regole RE2 → default del receiver
- ✅ Confronto delle severity con l'ordinamento nativo dell'enum Postgres, nessuna funzione di mapping
- ✅ `updated_at` sulle sole tabelle di configurazione
- ✅ Cancellazione di un Group non vuoto: cascade, preceduta da `delete-impact` e conferma per nome
- ✅ Abbassare il cap del tenant sotto quello di un receiver: `409`, nessun adeguamento silenzioso
- ✅ Colonne di quota (`max_notifications_per_day`, `max_storage_bytes`) presenti da F1, enforcement in F7

**Sicurezza e isolamento**
- ✅ Multi-tenant con RLS, `current_setting('app.tenant_id', true)`, default deny
- ✅ Tre ruoli Postgres (`app`, `ingest`, `auth`), **nessun `BYPASSRLS`** nel sistema
- ✅ Email unica globale: login non ambiguo, un utente in un solo tenant
- ✅ Ingest: **404 uniforme** per slug inesistente, receiver disabilitato e tenant sospeso; diagnostica via contatore in dashboard
- ✅ Rate limit per IP come primo gate, `rate_limit_per_min = 0` disattiva il solo limite per-slug
- ✅ Idempotenza opzionale su `X-Request-Id`, finestra Redis di 5 minuti, replay con `200`
- ✅ Regex utente eseguite con `google-re2`: ReDoS strutturalmente impossibile
- ✅ Token di invito solo nel body, mai nel path
- ✅ Vincolo ultimo owner
- ✅ Registrazione pubblica disabilitata di default, primo tenant da CLI
- ✅ `/metrics` e console MinIO su porte interne, non instradate da nginx
- ✅ Access token non revocabile prima della scadenza (15 min): accettato per l'MVP

**Infrastruttura**
- ✅ Stack: FastAPI + React + PostgreSQL + Redis + Celery + MinIO
- ✅ Worker Celery con engine SQLAlchemy sincrono, API async
- ✅ Enqueue dei task su hook `after_commit`, reconciler come garanzia di consegna
- ✅ Outbound reale verso Google Chat e Slack via Incoming Webhook, trigger a soglia di severità
- ✅ Canali configurati per Group con override sul Receiver
- ✅ Dashboard con polling REST nell'MVP, SSE in v2
- ✅ Retention: purge automatico configurabile per tenant
- ✅ SMTP opzionale, invito sempre disponibile come link copiabile

---

## 16. Rischi noti e rimandi consapevoli

Nessuna decisione architetturale resta aperta. Restano tre limiti dichiarati, da rivedere quando i numeri reali li renderanno stretti:

1. **Ricerca cieca dentro i payload offloaded.** Dalla migrazione 0015 il filtro `q` copre il contenuto intero dei payload inline, ma sopra `NOTIFYHUB_INLINE_MAX_BYTES` il corpo vive su MinIO e Postgres vede solo i 4096 caratteri di `content_preview`. Se la ricerca profonda anche lì diventa un requisito, la strada è un indice esterno (OpenSearch/Meilisearch) alimentato dal worker, non un `LIKE` su MinIO.
2. **Nessun partitioning di `notifications`.** Con volumi alti il purge notturno a batch da 10.000 righe diventerà il collo di bottiglia. Il passaggio a partizioni mensili è in F8, con l'accortezza sul trigger di cancellazione oggetti descritta in §11.
3. **Access token valido fino a 15 minuti dopo il logout.** Accettabile per un self-hosted; la denylist dei `jti` su Redis è la mitigazione già identificata.
