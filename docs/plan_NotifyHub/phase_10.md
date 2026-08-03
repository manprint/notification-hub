# Fase 9 — Dashboard React

> **Intent:** costruire la SPA che consuma l'API completata nelle fasi 3-8: consultazione, gestione, diagnostica.
> **Shippable alone?** si — la SPA gira in sviluppo contro l'API locale; il servizio nel compose arriva in fase 10.
> **Preconditions:** fase 8 DONE. L'API risponde su `http://localhost:8000`.

Fonti autoritative: `notifyhub-spec.md` sezione 9 (contratti degli endpoint), sezione 4.1 (matrice ruoli, che governa cosa mostrare), sezione 9.5 (limite della ricerca).

Regole della fase, oltre a quelle dell'overview:

- **Nessuna libreria oltre a quelle elencate in 9.1.** Niente framework CSS, niente librerie di componenti, niente gestori di stato globali oltre a TanStack Query (decisione D11).
- **Le fixture di MSW si copiano dalle risposte reali** dei test e2e del backend, non si inventano. Se una fixture non corrisponde alla risposta reale, il test e verde e l'applicazione e rotta.
- **Nessun testo in inglese nell'interfaccia**: l'applicazione parla italiano, coerentemente con la specifica. Gli identificatori nel codice restano in inglese.
- Nessuna emoji nell'interfaccia.

---

## Sub-phases

### 9.1 Scaffolding e catena dei gate del frontend

- **Model:** Haiku
- **Files:** `frontend/` (nuovo albero).
- **Change:**
  1. Genera il progetto: `npm create vite@latest frontend -- --template react-ts`, poi `npm --prefix frontend install`.
  2. Installa **esattamente** queste dipendenze e nessun'altra:
     - runtime: `react-router-dom`, `@tanstack/react-query`;
     - sviluppo: `vitest`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `jsdom`, `msw`, `eslint`, `@typescript-eslint/parser`, `@typescript-eslint/eslint-plugin`, `eslint-plugin-react-hooks`.
  3. In `frontend/package.json` definisci gli script `dev`, `build`, `preview`, `lint` (`eslint src --max-warnings 0`), `test` (`vitest`).
  4. In `frontend/vite.config.ts` configura il proxy di sviluppo: `/api` e `/ingest` verso `http://localhost:8000`. Configura Vitest con `environment: "jsdom"`, `setupFiles: "./src/setupTests.ts"`, `globals: true`.
  5. `frontend/src/setupTests.ts` importa `@testing-library/jest-dom` e avvia il server MSW definito in 9.2.
  6. `frontend/src/styles.css` con le variabili di base: colori delle cinque severity (`critical` e `error` rosso, `warning` giallo, `info` e `debug` grigio), spaziature, tipografia. Un solo file, importato da `main.tsx`.
  7. Cancella i file di esempio generati da Vite (`App.css`, il logo, il contenuto di esempio di `App.tsx`).
- **Unit tests:** `frontend/src/__tests__/smoke.test.tsx` — renderizza un componente banale e asserisce che sia nel documento. Serve a dimostrare che la catena Vitest e configurata.
- **e2e tests:** nessuno.
- **Done:** `make fe-lint`, `make fe-test` e `make fe-build` terminano tutti con exit 0.

### 9.2 Client API tipizzato e gestione della sessione

- **Model:** Sonnet
- **Files:** `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/api/mocks/handlers.ts`, `frontend/src/api/mocks/server.ts` (tutti nuovi).
- **Pattern:** un solo punto di uscita HTTP. Nessun componente chiama `fetch` direttamente: se lo vedi, e un errore.
- **Change:**
  - `types.ts` dichiara le interfacce che rispecchiano gli schemi Pydantic delle fasi 3-8. I nomi dei campi sono identici a quelli JSON del backend, senza conversione a camelCase: una conversione automatica e una fonte di bug silenziosi.
  - `client.ts` espone `apiGet`, `apiPost`, `apiPatch`, `apiPut`, `apiDelete`, tipizzati con generici. Responsabilita:
    - aggiunge l'header `Authorization: Bearer <access_token>` letto dalla memoria del modulo;
    - su `401`, tenta **una sola volta** il refresh chiamando `POST /api/v1/auth/refresh`, poi ripete la richiesta originale; se anche il refresh fallisce, cancella la sessione e reindirizza a `/login`. Il ciclo di refresh deve essere protetto da una promessa condivisa, altrimenti dieci richieste parallele scatenano dieci rotazioni e la rilevazione del riuso del backend revoca l'intera famiglia;
    - traduce il corpo RFC 7807 in un oggetto `ApiError` con `status`, `type`, `title`, `detail`, cosi l'interfaccia puo mostrare il `detail` reale invece di un messaggio generico.
  - Il refresh token si conserva in `localStorage`, l'access token solo in memoria: cosi un ricaricamento della pagina non costringe a rifare il login, ma l'access token non resta su disco.
  - `mocks/handlers.ts` definisce i gestori MSW usati dai test, con le fixture copiate dalle risposte reali.
- **Unit tests:** in `frontend/src/api/__tests__/client.test.ts`:
  `test_refresh_una_sola_volta` — cinque richieste parallele che ricevono `401` producono **una sola** chiamata a `/auth/refresh`. Percorso negativo: fallisce se manca la promessa condivisa.
  `test_refresh_fallito_pulisce_la_sessione` — se il refresh restituisce `401`, il token viene rimosso e viene emesso l'evento di logout.
  `test_errore_problem_json_tradotto` — una risposta `422` con corpo RFC 7807 produce un `ApiError` con `detail` valorizzato.
- **e2e tests:** nessuno.
- **Done:** i tre test passano.

### 9.3 Instradamento, struttura di pagina, guardia dei ruoli, accesso

- **Model:** Sonnet
- **Files:** `frontend/src/App.tsx`, `frontend/src/hooks/useSession.ts`, `frontend/src/components/Layout.tsx`, `frontend/src/components/RequireRole.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/AcceptInvitePage.tsx` (tutti nuovi).
- **Change:**
  - rotte: `/login`, `/invite`, `/` (riepilogo), `/notifications`, `/notifications/:id`, `/groups`, `/receivers/:id`, `/channels`, `/deliveries`, `/settings`, `/users`.
  - `useSession` espone utente corrente, ruolo, `login`, `logout`; carica il profilo da `GET /api/v1/auth/me`.
  - `RequireRole` e un componente di avvolgimento che, dato un insieme di ruoli ammessi, mostra i figli oppure un messaggio di accesso negato. **La corrispondenza con la matrice ruoli della specifica sezione 4.1 e vincolante**: la voce di menu e la rotta si nascondono insieme. Nascondere solo il pulsante e lasciare la rotta raggiungibile e un errore.
  - `LoginPage`: email e password, gestione di `429` con il messaggio "troppi tentativi, riprova fra N minuti".
  - `AcceptInvitePage`: legge il token dal **frammento** dell'URL (`window.location.hash`), non dalla query, coerentemente con la specifica sezione 9.2. Chiede la password (minimo 12 caratteri, validato lato client come lato server) e invia il token nel **corpo** della richiesta.
- **Unit tests:** in `frontend/src/__tests__/routing.test.tsx`:
  `T-UI1` `test_utente_non_autenticato_va_al_login` — visitando `/notifications` senza sessione si finisce su `/login`.
  `T-UI2` `test_viewer_non_vede_la_voce_canali` — con ruolo `viewer`, la voce di menu "Canali" non e nel documento e la rotta `/channels` mostra l'accesso negato. Percorso negativo della matrice ruoli.
  `T-UI3` `test_token_invito_letto_dal_frammento` — con `#token=abc`, la pagina invia `abc` nel corpo della chiamata di accettazione e **non** nella query string.
- **e2e tests:** nessuno in questa fase; il percorso reale di accesso e coperto dallo smoke test di fase 10 sotto-fase 10.4.
- **Done:** i tre test passano.

### 9.4 Componenti comuni

- **Model:** Haiku
- **Files:** `frontend/src/components/SeverityBadge.tsx`, `StatusPill.tsx`, `DataTable.tsx`, `ConfirmDialog.tsx`, `EmptyState.tsx`, `ErrorBanner.tsx` (tutti nuovi).
- **Pattern:** componenti presentazionali puri, nessuna chiamata di rete, nessuno stato globale.
- **Change:**
  - `SeverityBadge` — riceve una severity e applica il colore della specifica sezione 8.5.
  - `StatusPill` — stati di lettura e di consegna.
  - `DataTable` — tabella con intestazioni, corpo, stato di caricamento e pulsante "carica altri" per la paginazione a cursore. **Non implementa la paginazione a numero di pagina**: l'API non la supporta.
  - `ConfirmDialog` — riceve un `expectedText` e abilita la conferma solo quando l'utente lo digita esattamente. E il componente usato per la cancellazione dei gruppi.
  - `EmptyState` e `ErrorBanner` — messaggi uniformi; `ErrorBanner` mostra il `detail` dell'`ApiError`.
- **Unit tests:** in `frontend/src/components/__tests__/`:
  `T-UI4` `test_confirm_richiede_testo_esatto` — il pulsante resta disabilitato con testo parziale o diverso, si abilita solo con la corrispondenza esatta. Percorso negativo.
  `T-UI5` `test_badge_colore_per_severity` — cinque asserzioni sulla classe applicata.
- **e2e tests:** nessuno (componenti presentazionali puri, nessun comportamento osservabile end-to-end).
- **Done:** i due test passano.

### 9.5 Pagina di riepilogo

- **Model:** Sonnet
- **Files:** `frontend/src/pages/HomePage.tsx` (nuovo).
- **Change:** consuma `GET /api/v1/stats/summary`. Mostra: non lette totali, ripartizione per severity, tabella per gruppo con totale e non lette, notifiche nelle ultime 24 ore, numero di consegne in stato `dead` con collegamento a `/deliveries?status=dead`. Aggiornamento con polling ogni 30 secondi tramite `refetchInterval` di TanStack Query, coerentemente con la scelta della specifica di usare polling nell'MVP.
- **Unit tests:** `T-UI6` `test_home_mostra_conteggi` — con la fixture di riepilogo, i numeri compaiono a schermo e la ripartizione ha cinque voci.
- **e2e tests:** nessuno in questa fase; la home reale e verificata dalla prova manuale del criterio di conclusione.
- **Done:** il test passa.

### 9.6 Lista delle notifiche

- **Model:** Sonnet
- **Files:** `frontend/src/pages/NotificationsPage.tsx`, `frontend/src/hooks/useNotifications.ts` (nuovi).
- **Change:** filtri per gruppo, receiver, stato, severity minima, intervallo di date e ricerca testuale; paginazione a cursore con `useInfiniteQuery`; azioni di marcatura come letta singola e massiva.
  Accanto al campo di ricerca **deve** comparire la nota: "la ricerca esamina i primi 4096 caratteri del contenuto". E un limite dichiarato della specifica sezione 9.5 e nasconderlo genera segnalazioni di bug che non lo sono.
  Le notifiche con `content_normalized` a `true` mostrano un contrassegno "contenuto normalizzato"; quelle con `storage_backend` uguale a `object` un contrassegno con la dimensione.
- **Unit tests:** in `frontend/src/pages/__tests__/notifications.test.tsx`:
  `T-UI7` `test_carica_altri_usa_il_cursore` — il secondo caricamento invia il `next_cursor` restituito dal primo e i risultati si accodano senza duplicati.
  `T-UI8` `test_nota_sulla_ricerca_presente` — il testo sui 4096 caratteri e nel documento. Percorso negativo: fallisce se qualcuno lo rimuove.
  `T-UI9` `test_filtri_nella_query` — selezionati gruppo e severity minima, la richiesta contiene entrambi i parametri.
- **e2e tests:** nessuno in questa fase; la lista contro l'API reale e verificata dalla prova manuale del criterio di conclusione.
- **Done:** i tre test passano.

### 9.7 Dettaglio della notifica

- **Model:** Sonnet
- **Files:** `frontend/src/pages/NotificationDetailPage.tsx` (nuovo).
- **Change:** mostra metadati completi, la catena di severity (`severity_source` e, se `rule`, il pattern che ha vinto), e il contenuto. Se `storage_backend` e `inline` il contenuto e a schermo; se e `object` compare un pulsante "Scarica contenuto completo" che punta a `content_url`, con la dimensione indicata. **Nessun tentativo di renderizzare 20MB nel DOM.** Azioni: segna come letta, elimina (solo per i ruoli ammessi).
- **Unit tests:** `T-UI10` `test_payload_offloaded_mostra_download` — con `storage_backend: "object"` compare il pulsante di scaricamento e il corpo **non** viene renderizzato. Percorso negativo.
  `T-UI11` `test_origine_severity_mostrata` — con `severity_source: "rule"` compare il pattern vincente.
- **e2e tests:** nessuno in questa fase; lo scaricamento reale di un payload da 2MB e coperto dal passo 15 dello smoke test di fase 10.
- **Done:** i due test passano.

### 9.8 Gruppi, receiver e regole di severity

- **Model:** Sonnet
- **Files:** `frontend/src/pages/GroupsPage.tsx`, `frontend/src/pages/ReceiverDetailPage.tsx` (nuovi).
- **Change:**
  - elenco e creazione dei gruppi; cancellazione con `ConfirmDialog` alimentato da `GET /groups/{id}/delete-impact`, mostrando i conteggi reali e richiedendo di digitare il nome del gruppo;
  - dettaglio del receiver: slug con pulsante di copia e il comando `curl` pronto all'uso, stato, limiti, `rejected_last_24h` mostrato come avviso quando il receiver e disabilitato;
  - rotazione dello slug dietro conferma esplicita, visibile solo ad admin e owner;
  - CRUD delle regole di severity con l'ordine di priorita, e il riquadro di prova che chiama `POST /receivers/{id}/test-severity` mostrando severity risolta e regola vincente;
  - il messaggio di errore `422` sulla sintassi RE2 va mostrato per intero: e l'unico modo in cui l'utente capisce perche il suo lookahead e stato rifiutato.
- **Unit tests:** `T-UI12` `test_cancellazione_gruppo_mostra_impatto` — la finestra di conferma riporta i conteggi della fixture e il pulsante e disabilitato finche il nome non e digitato esattamente.
  `T-UI13` `test_prova_severity_mostra_regola` — la risposta di prova compare a schermo con il nome della regola.
  `T-UI14` `test_rotate_slug_nascosto_al_member` — con ruolo `member`, il pulsante non e nel documento. Percorso negativo della matrice ruoli.
- **e2e tests:** nessuno in questa fase; la creazione reale di gruppo e receiver e coperta dai passi 4 e 5 dello smoke test di fase 10.
- **Done:** i tre test passano.

### 9.9 Canali, binding e override

- **Model:** Sonnet
- **Files:** `frontend/src/pages/ChannelsPage.tsx` (nuovo), `frontend/src/components/ChannelBindings.tsx` (nuovo).
- **Change:** creazione e modifica dei canali; **il webhook si mostra solo come `webhook_hint`**, mai in chiaro, e il campo di inserimento e di tipo password e resta vuoto in modifica; pulsante "Invia messaggio di prova" con esito a schermo; diagnostica `last_success_at`, `last_error_at`, `last_error`. Gestione dei binding di gruppo con la soglia, e degli override di receiver con le due modalita, dove `min_severity` compare solo per `override`.
- **Unit tests:** `T-UI15` `test_webhook_mai_in_chiaro` — nella pagina renderizzata con una fixture di canale, la URL completa non compare in nessun nodo di testo ne in alcun attributo `value`. Percorso negativo dell'invariante I-6.
  `T-UI16` `test_mute_nasconde_la_soglia` — scegliendo `mute`, il campo `min_severity` sparisce dal modulo.
- **e2e tests:** nessuno in questa fase; la creazione reale del canale e coperta dal passo 6 dello smoke test di fase 10, che asserisce anche l'assenza del webhook in chiaro nella risposta.
- **Done:** i due test passano.

### 9.10 Consegne, impostazioni del tenant, membri

- **Model:** Sonnet
- **Files:** `frontend/src/pages/DeliveriesPage.tsx`, `frontend/src/pages/SettingsPage.tsx`, `frontend/src/pages/UsersPage.tsx` (nuovi).
- **Change:**
  - `DeliveriesPage`: elenco filtrabile per stato e canale, con il dettaglio dell'errore e il pulsante di ri-accodamento visibile solo sulle righe `dead` e solo per i ruoli ammessi;
  - `SettingsPage` (solo owner): retention, cap del corpo, quote. Sul `409` di conflitto mostra l'elenco dei receiver in conflitto restituito dall'API, con il rispettivo `max_body_bytes`: e l'informazione che serve a risolvere, e va mostrata, non riassunta in "operazione non riuscita";
  - `UsersPage` (admin e owner): elenco dei membri, cambio ruolo, rimozione, creazione inviti con il pulsante "copia link" sempre presente e l'indicazione se l'email e stata inviata. Sul `409` dell'ultimo owner mostra un messaggio esplicito.
- **Unit tests:** `T-UI17` `test_retry_solo_su_dead` — il pulsante compare sulle righe `dead` e non sulle altre. Percorso negativo.
  `T-UI18` `test_conflitto_cap_elenca_i_receiver` — con una risposta `409` che contiene `conflicting_receivers`, i nomi compaiono a schermo.
  `T-UI19` `test_link_invito_sempre_copiabile` — con `email_sent: false`, il pulsante di copia c'e ugualmente e il collegamento e visibile.
- **e2e tests:** nessuno in questa fase; le stesse risposte dell'API sono gia coperte da `T-OUT22`..`T-OUT25`, `T-MGMT15` e `T-AUTH14` lato backend.
- **Done:** i tre test passano; `make fe-lint`, `make fe-test`, `make fe-build` verdi.

---

## Files touched (this phase)

- `frontend/` — creato — intero albero generato da Vite e ripulito
- `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `.eslintrc.cjs` — creati o modificati — configurazione e script
- `frontend/src/styles.css`, `main.tsx`, `App.tsx`, `setupTests.ts` — creati
- `frontend/src/api/client.ts`, `types.ts`, `mocks/handlers.ts`, `mocks/server.ts` — creati
- `frontend/src/hooks/useSession.ts`, `useNotifications.ts` — creati
- `frontend/src/components/Layout.tsx`, `RequireRole.tsx`, `SeverityBadge.tsx`, `StatusPill.tsx`, `DataTable.tsx`, `ConfirmDialog.tsx`, `EmptyState.tsx`, `ErrorBanner.tsx`, `ChannelBindings.tsx` — creati
- `frontend/src/pages/LoginPage.tsx`, `AcceptInvitePage.tsx`, `HomePage.tsx`, `NotificationsPage.tsx`, `NotificationDetailPage.tsx`, `GroupsPage.tsx`, `ReceiverDetailPage.tsx`, `ChannelsPage.tsx`, `DeliveriesPage.tsx`, `SettingsPage.tsx`, `UsersPage.tsx` — creati
- `frontend/src/**/__tests__/` — creati — `T-UI1` .. `T-UI19`

---

## Phase gates

- **Lint:** `make fe-lint` (zero warning ammessi)
- **Test:** `make fe-test`
- **Build:** `make fe-build`
- **Regression guard:** i gate del backend restano verdi: `make gates`.

## Phase done criterion

`make fe-lint && make fe-test && make fe-build` verdi con `T-UI1` .. `T-UI19`. Verifica manuale: con backend e frontend in esecuzione, si accede con l'owner creato dal bootstrap, si crea un gruppo e un receiver, si invia una notifica con `curl` e compare nella lista entro il ciclo di polling. Nessuna pagina mostra un webhook in chiaro e nessuna voce di menu vietata dalla matrice ruoli e raggiungibile.
