# Phase 1 — Frontend: lista notifiche

> **Intent:** In `/notifications` ogni riga mostra due pill (stato lettura + stato verified) e due pulsanti di toggle (lettura, verifica), con stile consistente al resto dell'app.
> **Shippable alone?** yes — il backend di phase_0 fornisce gia' il campo `verified`; se il backend non e' deployato i mock msw coprono i test.
> **Preconditions:** phase_01 DONE.

React 18 + TypeScript + TanStack Query + Vitest + Testing Library + msw. Segui lo stile dei file esistenti (etichette UI in italiano, classi CSS esistenti, nessun commento decorativo).

---

## Sub-phases

### 1.1 Tipi + fixture msw + handler PATCH globale
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — implementazione.
- **Files:**
  - `frontend/src/api/types.ts:304` (ListItemOut `status`), `:328` (DetailOut `status`)
  - `frontend/src/api/mocks/handlers.ts:37-68` (fixture page1), `:70-88` (page2), `:90-107` (detail inline), `:109-126` (detail object), `:414-420` (handlers lista/dettaglio)
- **Change:**
  1. In `frontend/src/api/types.ts` aggiungi `verified: boolean;` subito dopo `status: NotificationStatus;` in `NotificationListItemOut` (riga 304) e in `NotificationDetailOut` (riga 328).
  2. In `frontend/src/api/mocks/handlers.ts` aggiungi `verified` a TUTTE le fixture di notifica:
     - `fixtureNotificationsPage1`: `n1` (riga 49, status unread) -> `verified: true`; `n2` (riga 62, status read) -> `verified: false`.
     - `fixtureNotificationsPage2`: `n3` (riga 82) -> `verified: false`.
     - `fixtureNotificationDetailInline` (riga 104) -> `verified: true` (coerente con n1).
     - `fixtureNotificationDetailObject` (riga 123) -> `verified: false`.
  3. Aggiungi un handler PATCH globale (dopo l'handler GET dettaglio, riga ~420):
     ```ts
     http.patch("/api/v1/notifications/:id", async ({ request, params }) => {
       const body = (await request.json()) as { status?: string; verified?: boolean };
       const base =
         String(params.id) === "n4"
           ? { ...fixtureNotificationDetailObject, ...body }
           : { ...fixtureNotificationDetailInline, ...body };
       return HttpResponse.json(base);
     }),
     ```
     Il typecheck di `handlers.ts` richiede che ogni fixture abbia `verified`, quindi fai l'editing di questo passo PRIMA di 1.2.
- **Unit tests:** nessun nuovo test qui (il coverage arriva in 1.3).
- **e2e tests:** T-LIST* in 1.3.
- **Done:** `make fe-build` compila (`tsc -b && vite build`) senza errori.

### 1.2 Pagina `NotificationsPage`: setStatus/setVerified, colonna azioni, pill
- **Model:** `frontend/src/pages/NotificationsPage.tsx:66-69` (markRead), `:125-134` (colonne Stato + azioni).
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; `agent-1` self-review dell'accettazione UI (D5/D6).
- **Change:**
  1. Sostituisci `markRead` (righe 66-69) con:
     ```ts
     async function setStatus(id: string, status: NotificationStatus) {
       await apiPatch(`/api/v1/notifications/${id}`, { status });
       await queryClient.invalidateQueries({ queryKey: ["notifications"] });
     }

     async function setVerified(id: string, verified: boolean) {
       await apiPatch(`/api/v1/notifications/${id}`, { verified });
       await queryClient.invalidateQueries({ queryKey: ["notifications"] });
     }
     ```
     `NotificationStatus` e' gia' importato (riga 9). `bulkRead` resta invariato.
  2. Colonna "Stato" (righe 125-126): al posto di `render: (n) => <StatusPill status={n.status} />` usa:
     ```ts
     render: (n) => (
       <>
         <StatusPill status={n.status} />
         <span className={`status-pill${n.verified ? " verified" : ""}`} style={{ marginLeft: 6 }}>
           {n.verified ? "Verificata" : "Non verificata"}
         </span>
       </>
     ),
     ```
     (il `style marginLeft: 6` ricalca il pattern gia' usato alle righe 91 e 115).
  3. Colonna azioni (righe 127-134): sostituisci la render con due pulsanti sempre visibili:
     ```ts
     render: (n) => (
       <div className="row-actions">
         <button onClick={() => void setStatus(n.id, n.status === "unread" ? "read" : "unread")}>
           {n.status === "unread" ? "Segna come letta" : "Segna come non letta"}
         </button>
         <button onClick={() => void setVerified(n.id, !n.verified)}>
           {n.verified ? "Segna come non verificata" : "Segna come verificata"}
         </button>
       </div>
     ),
     ```
  4. In `frontend/src/styles.css`, subito dopo il blocco `button.primary` (riga 69-72), aggiungi la classe per le azioni di riga e la variante pill:
     ```css
     .row-actions {
       display: flex;
       gap: var(--space-2);
       align-items: center;
       flex-wrap: wrap;
     }

     .status-pill.verified {
       background: var(--color-accent);
       border-color: var(--color-accent);
       color: #fff;
     }
     ```
     Niente nuove variabili di colore: si riusa `--color-accent` (coerente con `button.primary`).
- **Unit tests:** nessuno qui (UI test in 1.3).
- **e2e tests:** T-LIST* in 1.3.
- **Done:** `make fe-build` verde; manualmente la riga mostra pill e due pulsanti con etichette commutate in base a status/verified.

### 1.3 Test UI della lista
- **Model:** `frontend/src/pages/__tests__/notifications.test.tsx` (esistente; pattern `server.use` + `renderWithProviders`).
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; agente-1 self-review delle asserzioni.
- **Change:** aggiungi in `describe("NotificationsPage", ...)` questi test (usando `server.use` per override puntuali; `server` importato riga 6):
  1. `T-LIST1 "le etichette commutano in base a status"`: con fixture default, la riga n1 (unread) mostra il pulsante `Segna come letta`, la riga n2 (read) mostra `Segna come non letta`. Usa `within(screen.getByRole("table"))` per isolare le celle (pattern gia' usato alle righe 108-110).
  2. `T-LIST2 "segna come non letta manda status unread"`: cattura la richiesta PATCH con `server.use(http.patch(...))` (come righe 175-178) e assert su `{ status: "unread" }`; opzionale override GET che restituisca la riga aggiornata.
  3. `T-LIST3 "toggle verifica manda verified true e mostra la pill"`: PATCH catturato -> body `{ verified: true }`; dopo il refetch la cella contiene `Verificata` (override GET che restituisce `verified: true`).
  4. `T-LIST4 "le pill Verificata/Non verificata sono presenti"`: con la fixture default (n1 verified true, n2 verified false) la tabella contiene sia `Verificata` sia `Non verificata`.
- **Unit tests:** T-LIST1..T-LIST4 (Vitest + Testing Library).
- **e2e tests:** nessuno aggiuntivo (il comportamento di persistenza e' coperto da T-VER* in phase_01).
- **Done:** `make fe-test` verde (tutti i test della lista passano).

---

## Phase gates

- **Lint:** `make fe-lint`
- **Test:** `make fe-test`
- **Build:** `make fe-build`
- **Regression guard:** T-UI7, T-UI8, T-UI9 e il test bulk-read esistente in `notifications.test.tsx` devono restare verdi (nessun assert rimosso).

## Phase done criterion

`make fe-lint fe-test fe-build` verdi. Ogni riga della lista mostra pill stato + pill verified e i due pulsanti di toggle; i 4 nuovi test T-LIST* passano.