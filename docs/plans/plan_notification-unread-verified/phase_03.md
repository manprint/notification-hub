# Phase 2 — Frontend: dettaglio notifica

> **Intent:** In `/notifications/{id}` gli stessi toggle (lettura e verifica) e le stesse pill del elenco, con layout coerente.
> **Shippable alone?** yes — dipende solo dalle fixture/types di phase_01 (gia' presenti).
> **Preconditions:** phase_02 DONE.

> **Behavior change (importante):** il test esistente `"segna come letta e il pulsante sparisce"` (in `frontend/src/pages/__tests__/notificationDetail.test.tsx`, righe 114-136) asseriva che dopo il click il pulsante SPARISCE. Con il nuovo UX (D5) il pulsante resta e diventa "Segna come non letta". Il test va riscritto in sub-phase 2.2. E' l'unico test del progetto che cambia; tutti gli altri assert di dettaglio restano.

---

## Sub-phases

### 2.1 Pagina `NotificationDetailPage`: setStatus/setVerified, pill, toolbar
- **Model:** `frontend/src/pages/NotificationDetailPage.tsx:31-34` (markRead), `:59` (riga badge/status), `:106-111` (toolbar).
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; agente-1 self-review del layout (D6).
- **Change:**
  1. Sostituisci `markRead` (righe 31-34) con:
     ```ts
     async function setStatus(status: NotificationStatus) {
       await apiPatch(`/api/v1/notifications/${id}`, { status });
       await queryClient.invalidateQueries({ queryKey: ["notification", id] });
     }

     async function setVerified(verified: boolean) {
       await apiPatch(`/api/v1/notifications/${id}`, { verified });
       await queryClient.invalidateQueries({ queryKey: ["notification", id] });
     }
     ```
     Aggiungi `NotificationStatus` all'import di tipo dalla riga 4: `import type { ApiError, NotificationDetailOut, NotificationStatus } from "../api/types";`
  2. Riga header (riga 59): accanto a `<StatusPill status={data.status} />` aggiungi la pill di verifica:
     ```tsx
     <StatusPill status={data.status} />{" "}
     <span className={`status-pill${data.verified ? " verified" : ""}`}>
       {data.verified ? "Verificata" : "Non verificata"}
     </span>
     ```
  3. Toolbar (righe 106-111): aggiungi i due toggle PRIMA del pulsante Elimina, sostituendo la riga 107:
     ```tsx
     <button onClick={() => void setStatus(data.status === "unread" ? "read" : "unread")}>
       {data.status === "unread" ? "Segna come letta" : "Segna come non letta"}
     </button>
     <button onClick={() => void setVerified(!data.verified)}>
       {data.verified ? "Segna come non verificata" : "Segna come verificata"}
     </button>
     ```
     Il blocco Elimina (righe 108-110) resta invariato. Il layout `.toolbar` (flex con gap) gestisce i tre pulsanti senza modifiche CSS.
- **Unit tests:** nessuno qui.
- **e2e tests:** T-DET* in 2.2.
- **Done:** `make fe-build` verde.

### 2.2 Test dettaglio: riscrittura + nuovi
- **Model:** `frontend/src/pages/__tests__/notificationDetail.test.tsx` (righe 114-136: test "segna come letta e il pulsante sparisce"; righe 207-230: test viewer).
- **Assignment:** `agent:deepseek-v4-flash` — implementazione; agente-1 self-review (l'unico test del progetto che cambia).
- **Change:**
  1. Riscrivi il test righe 114-136 in `T-DET3 "segna come letta commuta in segna come non letta"`:
     - stesso setup (serve `stato = "unread"`, GET e PATCH catturati, righe 116-127).
     - click su "Segna come letta" -> assert `inviato` = `{ status: "read" }`.
     - dopo il refetch: il pulsante "Segna come letta" NON esiste piu' e compare "Segna come non letta".
     - click su "Segna come non letta" -> assert `inviato` = `{ status: "unread" }`.
  2. Aggiungi `T-DET1 "il dettaglio mostra entrambi i toggle"`: con `fixtureNotificationDetailInline` (verified true) presenti i pulsanti "Segna come letta" (status unread) e "Segna come non verificata", e la pill "Verificata".
  3. Aggiungi `T-DET2 "toggle verifica manda verified true"`: cattura PATCH con stato fixture verified false (`serviDettaglio({ ...fixtureNotificationDetailInline, verified: false })`), click "Segna come verificata" -> assert `{ verified: true }`; dopo refetch la pill e' "Verificata".
  4. Il test viewer (righe 207-230) resta valido ma ora mostra anche "Segna come verificata": NON modificare gli assert esistenti; se vuoi, aggiungi un assert che il viewer veda anche "Segna come verificata" (stesso diritto di segnare, non e' un'azione distruttiva).
- **Unit tests:** T-DET1, T-DET2, T-DET3.
- **e2e tests:** nessuno aggiuntivo.
- **Done:** `make fe-test` verde; i test pre-esistenti del dettaglio (download, origine severity, eliminazione, viewer, 404) restano verdi.

---

## Phase gates

- **Lint:** `make fe-lint`
- **Test:** `make fe-test`
- **Build:** `make fe-build`
- **Regression guard:** T-UI10, T-UI11 e gli altri test di `notificationDetail.test.tsx` restano verdi.

## Phase done criterion

`make fe-lint fe-test fe-build` verdi. Il dettaglio mostra pill stato + pill verified, i tre pulsanti (lettura, verifica, elimina se permesso) e i toggle commutano senza regredire il resto della pagina.