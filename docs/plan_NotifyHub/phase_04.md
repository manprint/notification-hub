# Fase 3 — Autenticazione e identita

> **Intent:** rendere il sistema utilizzabile da un essere umano: creazione del primo tenant da CLI, login, rotazione dei refresh token, ruoli, inviti, vincolo dell'ultimo owner.
> **Shippable alone?** si — al termine ci si autentica e si gestiscono i membri, senza ancora alcuna entita di dominio.
> **Preconditions:** fase 2 DONE.

Fonti autoritative: `notifyhub-spec.md` sezione 4.1 (matrice ruoli, vincolo ultimo owner), sezione 5.3 (meccanica dei pool), sezione 9.2 (superficie API), sezione 10.2 (requisiti di sicurezza).

Regola che vale per tutta la fase: **le tabelle di identita si leggono prima dell'autenticazione con il pool `auth_session()`, in sola lettura e sempre per chiave univoca; ogni scrittura successiva avviene in una nuova transazione `tenant_session(tenant_id)`.** Questa e la meccanica della specifica sezione 5.3 e non ha alternative.

---

## Sub-phases

### 3.1 Schemi Pydantic di autenticazione e utenti

- **Model:** Haiku
- **Files:** `backend/app/schemas/auth.py` (nuovo), `backend/app/schemas/user.py` (nuovo).
- **Pattern:** modelli Pydantic v2 con `model_config = ConfigDict(from_attributes=True)` per quelli di risposta. Suffissi obbligatori e uniformi in tutto il progetto: `...In` per il corpo delle richieste, `...Out` per le risposte.
- **Change:** definisci, senza logica:
  - `LoginIn` (`email: EmailStr`, `password: str`), `TokenPairOut` (`access_token`, `refresh_token`, `token_type="bearer"`, `expires_in: int`);
  - `RefreshIn` (`refresh_token: str`), `LogoutIn` (`refresh_token: str`);
  - `MeOut` (`id`, `email`, `role`, `tenant_id`, `tenant_name`);
  - `UserOut` (`id`, `email`, `role`, `status`, `last_login_at`), `UserPatchIn` (`role: UserRole | None`, `status: UserStatus | None`);
  - `InvitationIn` (`email: EmailStr`, `role: UserRole`), `InvitationOut` (`id`, `email`, `role`, `expires_at`, `invite_url: str`, `email_sent: bool`);
  - `InvitationAcceptIn` (`token: str`, `password: str`).
  **Nessuno schema di risposta contiene `password_hash`, `token_hash` o il refresh token in chiaro** oltre a `TokenPairOut`, che e l'unico punto in cui il refresh token esce (invariante I-6).
  La validazione della password minima 12 caratteri va messa qui come `Field(min_length=12)` su `InvitationAcceptIn.password` e su ogni altro punto in cui una password viene impostata.
- **Unit tests:** `backend/tests/unit/test_schemas_auth.py::test_password_corta_rifiutata` — `InvitationAcceptIn(token="t", password="corta")` solleva `ValidationError`. Test di percorso negativo.
  `test_user_out_non_espone_hash` — asserisce che `"password_hash" not in UserOut.model_fields`.
- **e2e tests:** nessuno.
- **Done:** `make types` verde.

### 3.2 Servizio di lookup pre-autenticazione

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/services/identity.py` (nuovo).
- **Pattern:** funzioni pure di lettura, ciascuna apre `auth_session()`, esegue una sola query per chiave univoca e restituisce una dataclass leggera, non un oggetto ORM attaccato a una sessione chiusa.
- **Change:** tre funzioni, e nessuna scrittura:
  ```python
  async def find_user_by_email(email: str) -> UserIdentity | None
  async def find_refresh_token(token_hash: str) -> RefreshTokenIdentity | None
  async def find_invitation(token_hash: str) -> InvitationIdentity | None
  ```
  `UserIdentity` e una dataclass con `id`, `tenant_id`, `email`, `password_hash`, `role`, `status`. Le altre due analoghe, con i campi che servono a decidere.
  Motivo del disegno: l'email e globalmente unica (specifica sezione 4.1), quindi una sola riga risolve il tenant. Da quel momento in poi tutto il resto del flusso usa `tenant_session(tenant_id)`.
  **Queste funzioni non verificano password ne scadenze.** Restituiscono i fatti; le decisioni stanno nell'endpoint. Tenere separate lettura e decisione e cio che rende testabile il percorso negativo.
- **Test strategy:** integrazione contro il database di test; le righe si creano con `tenant_session` e si leggono con il pool auth, cosi si verifica anche che i due ruoli vedano la stessa realta.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_identity.py` (marker `integration`):
  `T-AUTH1` `test_lookup_utente_per_email` — creato un utente nel tenant A, `find_user_by_email` lo trova e restituisce il `tenant_id` corretto **senza** che sia stata impostata alcuna GUC. E la dimostrazione che il pool `auth` funziona come previsto.
  `T-AUTH2` `test_lookup_email_inesistente` — restituisce `None`, non solleva.
  `T-AUTH3` `test_pool_auth_non_scrive` — un tentativo di INSERT eseguito sulla stessa sessione fallisce per privilegio insufficiente. Test di percorso negativo che protegge l'invariante I-1.
- **Done:** i tre test passano; `T-RLS8` resta verde.

### 3.3 Primitive di sicurezza

- **Model:** Sonnet
- **Files:** `backend/app/core/security.py` (nuovo).
- **Pattern:** funzioni pure, nessuno stato, nessun accesso al database.
- **Change:**
  - `hash_password(p: str) -> str` e `verify_password(p: str, h: str) -> bool` con `argon2.PasswordHasher()` ai parametri predefiniti della libreria. `verify_password` cattura `VerifyMismatchError` e restituisce `False`, non propaga.
  - `create_access_token(user_id, tenant_id, role) -> tuple[str, int]` — JWT HS256 firmato con `settings.notifyhub_secret_key`, claim esattamente `sub`, `tid`, `role`, `exp`, `iat`, `jti`; scadenza da `settings.access_token_ttl_minutes`. Restituisce il token e i secondi di validita.
  - `decode_access_token(token: str) -> AccessClaims` — verifica firma e scadenza, solleva `Problem(401, "/problems/unauthorized", ...)` su qualunque errore, senza distinguere fra token scaduto, malformato o con firma errata: la distinzione sarebbe un oracolo inutile.
  - `new_refresh_token() -> tuple[str, str]` — genera `secrets.token_urlsafe(32)` e restituisce `(token_in_chiaro, sha256_hex)`. Il chiaro esiste solo in memoria e nella risposta HTTP; in tabella va solo l'hash.
  - `hash_token(t: str) -> str` — SHA-256 esadecimale, usata anche per i token di invito.
- **Unit tests:** in `backend/tests/unit/test_security.py`:
  `test_password_roundtrip` — `verify_password(p, hash_password(p))` e `True`; con password sbagliata e `False`.
  `test_hash_non_deterministico` — due hash della stessa password differiscono (il sale c'e).
  `test_token_scaduto_rifiutato` — con `freezegun`, un token creato e poi verificato 16 minuti dopo fa sollevare `Problem` con status 401. Test di percorso negativo.
  `test_firma_alterata_rifiutata` — modificato un carattere della firma, `decode_access_token` solleva `Problem` 401.
  `test_refresh_token_hashato` — `new_refresh_token()` restituisce un hash che coincide con `hash_token` del chiaro, e il chiaro e lungo almeno 40 caratteri.
- **e2e tests:** nessuno.
- **Done:** i cinque test passano.

### 3.4 Login, rotazione del refresh, logout, limite sui tentativi

- **Model:** Sonnet
- **Files:** `backend/app/services/ratelimit.py` (nuovo), `backend/app/core/redis.py` (nuovo), `backend/app/api/v1/auth.py` (nuovo), `backend/app/main.py` (modificato).
- **Insertion point:** in `create_app()`, `app.include_router(auth.router, prefix="/api/v1")` va inserito immediatamente sopra il commento sentinella `# ROUTERS:`.
- **Pattern:** finestra scorrevole su Redis realizzata con un sorted set per chiave: si rimuovono gli elementi piu vecchi della finestra, si conta, si aggiunge il timestamp corrente, si imposta la scadenza. Le tre operazioni in una pipeline.
- **Change:**
  - `app/core/redis.py` espone `get_redis()` che restituisce un client asincrono singleton su `settings.redis_url`.
  - `app/services/ratelimit.py` espone **una sola** primitiva riusabile, che la fase 5 usera per l'ingestion senza riscriverla:
    ```python
    async def sliding_window_hit(key: str, limit: int, window_seconds: int) -> RateLimitResult
    ```
    `RateLimitResult` ha `allowed: bool`, `remaining: int`, `retry_after: int`. Se `limit <= 0` la funzione restituisce sempre `allowed=True` senza toccare Redis: e la semantica di "nessun limite" della specifica sezione 10.1.
  - `app/api/v1/auth.py` implementa:
    - `POST /auth/login` — limite `10` tentativi in `900` secondi sulla chiave `login:{email}:{ip}`; superato il limite risponde `429` con `Retry-After`. Poi `find_user_by_email`, `verify_password`, controllo `status == active` e `tenant.status == active`. **Su fallimento risponde sempre `401` con lo stesso corpo**, che si tratti di email inesistente, password errata o utente disabilitato. In caso di successo apre `tenant_session(tenant_id)`, aggiorna `last_login_at`, inserisce la riga `refresh_tokens` con `family_id` nuovo, e restituisce `TokenPairOut`.
    - `POST /auth/refresh` — `find_refresh_token(hash_token(input))`. Casi, nell'ordine: token inesistente -> `401`; token **gia revocato** -> riuso rilevato, si revoca l'intera `family_id` e si risponde `401`; token scaduto -> `401`. Altrimenti rotazione: dentro `tenant_session`, si valorizza `revoked_at` sulla riga vecchia e si inserisce una riga nuova con lo **stesso** `family_id`.
    - `POST /auth/logout` — revoca tutte le righe della famiglia del token fornito. Risponde `204` anche se il token non esiste, per non rivelarne l'esistenza.
    - `GET /auth/me` — richiede autenticazione (dipendenza della sotto-fase 3.5) e restituisce `MeOut`.
- **Test strategy:** e2e via `api_client`, con database e Redis reali. Prima di ogni test si azzerano le chiavi Redis del limite, con una fixture dedicata in `conftest.py`.
- **Unit tests:** `backend/tests/unit/test_ratelimit.py::test_limite_zero_significa_illimitato` — con `limit=0` la funzione restituisce `allowed=True` senza chiamare Redis (client sostituito con un finto che solleva se usato).
- **e2e tests:** in `backend/tests/e2e/test_auth.py`:
  `T-AUTH4` `test_login_riuscito` — credenziali valide restituiscono 200 con i due token e `expires_in == 900`.
  `T-AUTH5` `test_login_fallito_e_indistinguibile` — email inesistente, password errata e utente disabilitato producono tre risposte `401` con corpo byte-identico. Test di percorso negativo.
  `T-AUTH6` `test_limite_tentativi_login` — undici tentativi falliti consecutivi: l'undicesimo restituisce `429` con header `Retry-After`.
  `T-AUTH7` `test_rotazione_refresh` — un refresh restituisce una coppia nuova; il refresh vecchio non funziona piu.
  `T-AUTH8` `test_riuso_refresh_revoca_la_famiglia` — dopo una rotazione, riusare il token vecchio restituisce `401` **e** rende inutilizzabile anche il token nuovo. E il test che dimostra la rilevazione del riuso; fallisce se la revoca della famiglia viene rimossa.
  `T-AUTH9` `test_logout_revoca` — dopo il logout, il refresh restituisce `401`.
- **Done:** `make gates` verde con `T-AUTH1` .. `T-AUTH9`.

### 3.5 Dipendenze di autenticazione e autorizzazione

- **Model:** Haiku
- **Files:** `backend/app/api/deps.py` (nuovo).
- **Pattern:** dipendenze FastAPI componibili. La sessione di dominio si ottiene **solo** da qui, cosi nessun endpoint puo dimenticare `SET LOCAL`.
- **Change:**
  - `async def current_claims(authorization: str = Header(...)) -> AccessClaims` — estrae il bearer token, chiama `decode_access_token`. Header assente o malformato -> `Problem` 401.
  - `async def db(claims = Depends(current_claims)) -> AsyncIterator[AsyncSession]` — cede `tenant_session(claims.tid)`. **E l'unico modo autorizzato di ottenere una sessione dentro un endpoint autenticato.**
  - `def require_role(*roles: UserRole)` — fabbrica di dipendenze che confronta `claims.role` con l'insieme ammesso e solleva `Problem` 403 con `type=/problems/forbidden` se non appartiene.
  - Quattro alias pronti all'uso, che corrispondono alle righe della matrice ruoli della specifica sezione 4.1: `require_owner`, `require_admin` (owner, admin), `require_member` (owner, admin, member), `require_viewer` (tutti e quattro).
  Ogni endpoint delle fasi successive dichiara esattamente uno di questi quattro. Se un endpoint non ne dichiara nessuno, e un errore.
- **Unit tests:** `backend/tests/unit/test_deps.py::test_require_role_rifiuta` — `require_role(UserRole.owner)` con claim di ruolo `member` solleva `Problem` 403; con ruolo `owner` non solleva.
- **e2e tests:** `T-AUTH10` in `backend/tests/e2e/test_auth.py::test_me_richiede_token` — `GET /api/v1/auth/me` senza header restituisce `401`; con token valido restituisce 200 e `role` corretto.
- **Done:** `make gates` verde.

### 3.6 CLI di bootstrap e registrazione pubblica disattivata

- **Model:** Sonnet
- **Files:** `backend/app/cli.py` (nuovo), `backend/app/api/v1/auth.py` (modificato).
- **Pattern:** `argparse` con un sottocomando; nessuna dipendenza nuova.
- **Change:**
  - `python -m app.cli bootstrap --tenant-name NOME --email EMAIL [--password PWD]`. Sequenza obbligatoria:
    1. genera `tenant_id = uuid4()` in Python;
    2. apre `tenant_session(tenant_id)`;
    3. inserisce la riga `tenants` — la tabella e fuori da RLS, quindi l'INSERT passa;
    4. inserisce la riga `users` con ruolo `owner` — passa perche la GUC coincide con il `tenant_id` appena generato;
    5. se `--password` non e fornita, ne genera una con `secrets.token_urlsafe(16)` e la stampa **una sola volta** sullo standard output.
    Questo e il motivo per cui il bootstrap non ha bisogno di alcun privilegio speciale e l'invariante I-1 resta intatta.
    Se esiste gia un utente con quella email, esce con codice 1 e un messaggio, senza scrivere nulla.
  - In `auth.py`, `POST /auth/register`: se `settings.allow_public_registration` e `False` risponde **`403`** con `type=/problems/forbidden` e non tocca il database. Se e `True` esegue la stessa sequenza del bootstrap e restituisce `201` con la coppia di token.
- **Test strategy:** la CLI si prova invocando la funzione `main(argv)` in-process, non lanciando un sottoprocesso.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/integration/test_bootstrap.py` (marker `integration`):
  `T-AUTH11` `test_bootstrap_crea_tenant_e_owner` — dopo l'invocazione, esiste un tenant con quel nome e un utente `owner` con quella email, e il login con la password stampata riesce.
  `T-AUTH12` `test_bootstrap_email_duplicata` — la seconda invocazione con la stessa email esce con codice 1 e non crea nulla.
  `T-AUTH13` in `test_auth.py` `test_register_disattivata_per_default` — `POST /api/v1/auth/register` risponde `403`. Test di percorso negativo: fallisce se il flag viene invertito.
- **Done:** i tre test passano.

### 3.7 Gestione dei membri e vincolo dell'ultimo owner

- **Model:** Opus design review -> Sonnet implementa
- **Files:** `backend/app/api/v1/users.py` (nuovo), `backend/app/main.py` (modificato per la registrazione del router).
- **Pattern:** il controllo del vincolo e la modifica avvengono nella **stessa transazione**, con un lock esplicito sulla riga del tenant per serializzare due rimozioni concorrenti.
- **Change:**
  - `GET /api/v1/users` — `require_admin`. Elenco degli utenti del tenant.
  - `PATCH /api/v1/users/{id}` — `require_admin`. Consente di cambiare `role` e `status`.
  - `DELETE /api/v1/users/{id}` — `require_admin`. Rimozione.
  - **Guardia dell'ultimo owner**, applicata sia al PATCH che declassa un owner sia al DELETE di un owner sia al PATCH che lo disabilita:
    1. `SELECT ... FROM tenants WHERE id = :tid FOR UPDATE` — serializza;
    2. conta gli utenti con `role = 'owner'` e `status = 'active'`;
    3. se il conteggio e `1` e l'operazione riguarda proprio quell'utente, solleva `Problem(409, "/problems/last-owner", ...)` e la transazione va in rollback.
  Il lock sulla riga del tenant e obbligatorio: senza, due DELETE concorrenti passano entrambi il controllo e il tenant resta senza owner.
- **Test strategy:** il caso concorrente si verifica con due sessioni aperte in parallelo dentro il test, non simulandolo.
- **Unit tests:** nessuno.
- **e2e tests:** in `backend/tests/e2e/test_users.py`:
  `T-AUTH14` `test_rimozione_ultimo_owner_rifiutata` — con un solo owner nel tenant, `DELETE` su di lui restituisce `409` con `type` pari a `/problems/last-owner`, e l'utente esiste ancora. Test di percorso negativo.
  `T-AUTH15` `test_declassamento_ultimo_owner_rifiutato` — `PATCH` che porta l'unico owner a `admin` restituisce `409`.
  `T-AUTH16` `test_rimozione_owner_con_due_owner_riesce` — con due owner, la rimozione del primo restituisce `204`.
  `T-AUTH17` `test_member_non_puo_gestire_utenti` — con token di ruolo `member`, `GET /api/v1/users` restituisce `403`.
  `T-AUTH18` in `backend/tests/integration/test_users_concurrency.py` (marker `integration`) `test_due_rimozioni_concorrenti` — due transazioni che tentano di rimuovere due owner distinti su un tenant che ne ha esattamente due: una riesce, l'altra riceve `409`. Al termine il tenant ha ancora un owner. Fallisce se il `FOR UPDATE` viene tolto.
- **Done:** i cinque test passano.

### 3.8 Inviti

- **Model:** Sonnet
- **Files:** `backend/app/api/v1/invitations.py` (nuovo), `backend/app/services/mailer.py` (nuovo), `backend/app/main.py` (modificato).
- **Pattern:** il token in chiaro esiste solo nella risposta e nel link; in tabella va solo l'hash. Il link usa il frammento (`#token=`), che il browser non trasmette al server.
- **Change:**
  - `POST /api/v1/invitations` — `require_admin`. Genera `secrets.token_urlsafe(32)`, persiste `hash_token(...)`, scadenza a sette giorni. Costruisce `invite_url = f"{frontend_base}/invite#token={token}"`. Se `settings.smtp_enabled`, tenta l'invio con `app/services/mailer.py` e imposta `email_sent` di conseguenza; **un errore SMTP non fa fallire la richiesta**, l'invito resta valido e `email_sent` vale `false`. Risposta `201` con `InvitationOut`.
  - `POST /api/v1/invitations/accept` — **pubblico, token nel corpo**. Sequenza: `find_invitation(hash_token(body.token))`; se assente, scaduto o gia accettato -> `404` con corpo identico nei tre casi. Altrimenti apre `tenant_session(tenant_id)`, crea l'utente con il ruolo dell'invito, valorizza `accepted_at`, restituisce `201` con la coppia di token.
  - `app/services/mailer.py` espone `async def send_invitation(to: str, url: str) -> bool`, che restituisce `False` se SMTP non e configurato o se l'invio fallisce, senza sollevare.
  > **Attenzione, differenza rispetto a un'API convenzionale.** Il token non compare mai nel path: `POST /api/v1/invitations/{token}/accept` sarebbe un errore, perche finirebbe negli access log e nell'header Referer (specifica sezione 9.2).
- **Test strategy:** SMTP non configurato nell'ambiente di test, cosi il percorso predefinito e quello senza email.
- **Unit tests:** `backend/tests/unit/test_mailer.py::test_smtp_assente_ritorna_false` — con `smtp_host` vuoto, `send_invitation` restituisce `False` e non tenta connessioni.
- **e2e tests:** in `backend/tests/e2e/test_invitations.py`:
  `T-AUTH19` `test_invito_e_accettazione` — un admin invita, la risposta contiene `invite_url` con `#token=`, l'accettazione crea l'utente e il login funziona.
  `T-AUTH20` `test_token_non_in_tabella_in_chiaro` — dopo la creazione, una query diretta su `invitations` mostra che nessuna colonna contiene il token restituito dall'API. Test di percorso negativo che protegge l'invariante I-6.
  `T-AUTH21` `test_invito_scaduto_rifiutato` — con `freezegun` a otto giorni dopo, l'accettazione restituisce `404` con lo stesso corpo di un token inesistente.
  `T-AUTH22` `test_invito_usato_due_volte` — la seconda accettazione restituisce `404` e non crea un secondo utente.
- **Done:** `make gates` verde con tutti i `T-AUTH*`.

---

## Files touched (this phase)

- `backend/app/schemas/auth.py`, `user.py` — creati — schemi di richiesta e risposta
- `backend/app/services/identity.py` — creato — lookup pre-autenticazione sul pool auth
- `backend/app/core/security.py` — creato — Argon2, JWT, token opachi
- `backend/app/core/redis.py` — creato — client Redis singleton
- `backend/app/services/ratelimit.py` — creato — finestra scorrevole riusabile
- `backend/app/api/deps.py` — creato — claims, sessione, controllo dei ruoli
- `backend/app/api/v1/auth.py` — creato — login, refresh, logout, me, register
- `backend/app/api/v1/users.py` — creato — membri e vincolo ultimo owner
- `backend/app/api/v1/invitations.py` — creato — creazione e accettazione inviti
- `backend/app/services/mailer.py` — creato — invio opzionale via SMTP
- `backend/app/cli.py` — creato — comando `bootstrap`
- `backend/app/main.py` — modificato — registrazione dei tre router
- `backend/tests/unit/test_schemas_auth.py`, `test_security.py`, `test_ratelimit.py`, `test_deps.py`, `test_mailer.py` — creati
- `backend/tests/e2e/test_auth.py`, `test_users.py`, `test_invitations.py` — creati
- `backend/tests/integration/test_identity.py`, `test_bootstrap.py`, `test_users_concurrency.py` — creati
- `backend/tests/conftest.py` — modificato — fixture di pulizia Redis e fixture `authenticated_client`

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** `T-RLS1` .. `T-RLS9`, `T-CORE1` .. `T-CORE6` restano verdi.

## Phase done criterion

Da uno stack pulito: `make reset-db && make migrate && python -m app.cli bootstrap --tenant-name ACME --email a@b.it` stampa una password; il login con quella password restituisce una coppia di token; `GET /api/v1/auth/me` con l'access token restituisce ruolo `owner`. `T-AUTH8` dimostra la rilevazione del riuso dei refresh token, `T-AUTH14` e `T-AUTH18` il vincolo dell'ultimo owner anche in concorrenza, `T-AUTH13` che la registrazione pubblica e chiusa.
