# Phase 3 — Regressione, docs, polish layout

> **Intent:** Chiudere con porte tutte verdi, sincronizzare la spec, e verificare a occhio che il layout sia elegante e consistente.
> **Shippable alone?** yes.
> **Preconditions:** phase_03 DONE.

---

## Sub-phases

### 3.1 Suite completa + guardie di regressione
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — esecuzione; agente-1 self-review finale delle asserzioni di accettazione (gate di review).
- **Files:** nessuna modifica al codice; solo esecuzione.
- **Change:**
  1. Backend: `docker compose -f docker-compose.test.yml up -d` poi `make gates` (fmt-check, lint, types, test). Oltre ai nuovi T-VER*, devono passare: `test_patch_segna_letta_e_bulk_read` (I-4), `test_mark_status_schema`, `test_bulk_mark_read`.
  2. Frontend: `make fe-lint fe-test fe-build`.
  3. Applica la migrazione sul DB di test: `make migrate-test` e conferma che `0014` parta pulita (downgrade+upgrade senza errori).
- **Unit tests:** tutta la suite (guarda T-SCH*, T-VER*, T-LIST*, T-DET*).
- **e2e tests:** tutta la suite backend e2e (T-VER1..4, T-I4).
- **Done:** `make gates`, `make fe-lint fe-test fe-build` verdi; migrazione 0014 applicabile e downgradabile.

### 3.2 Sincronizzazione spec
- **Model:** `docs/notifyhub-spec.md` (sezioni: tabella `notifications` ~riga 255; §9.5 "segnare come lette" ~riga 127).
- **Assignment:** `agent:deepseek-v4-flash` — documentazione.
- **Change:**
  1. Nella tabella dei campi di `notifications` (riga 255, accanto a `status`): aggiungi riga `| verified | bool | default false | flag di verifica manuale dell'operatore; indipendente da status |`.
  2. Nel punto dove la spec descrive "Leggere notifiche, segnare come lette" (riga 127) e la consultazione: estendi la frase a "segnare come lette / non lette e come verificate / non verificate".
  3. Nessun altro doc: `docs/OPERAZIONI.md` non tocca il flusso (marcare `SKIPPED` in resume.md).
- **Unit tests:** nessuno (docs).
- **e2e tests:** nessuno.
- **Done:** la spec cita `verified` e i toggle; `git diff docs/notifyhub-spec.md` coerente.

### 3.3 Check manuale layout (agent-1 self-review)
- **Model:** `agent:deepseek-v4-flash`
- **Assignment:** `agent:deepseek-v4-flash` — revisione manuale marcata come self-review finale (gate di review del layout).
- **Files:** nessuno.
- **Change:** con `npm --prefix frontend run dev` e un backend up (o i mock msw in dev), verificare su `/notifications` e `/notifications/{id}`:
  1. Le pill (stato + verified) sono allineate e non si sovrappongono; il testo "Non verificata"/"Verificata" resta dentro la pill (padding coerente col resto).
  2. I due pulsanti della colonna azioni stanno in una riga, senza righe rotte su viewport largo; su viewport stretto si avvolgono senza sbavature (flex `.row-actions`).
  3. Colore verified (`--color-accent`) coerente con `button.primary`; la pill unverified ha lo stesso look delle altre pill neutre.
  4. Con righe unread e read mescolate la tabella non cambia altezza in modo stridente; il bordo hover dei pulsanti resta invariato.
  5. Nessun elemento sfugge a sinistra/destra della tabella; `DataTable` continua a scrollare/impaginare come prima.
  6. Comportamento: click su un toggle, pill e pulsante si aggiornano dopo il refetch; nessun flash di stato errato.
- **Unit tests:** nessuno.
- **e2e tests:** nessuno.
- **Done:** tutti i punti 1-6 verificati; eventuali ritocchi CSS sono solo dentro `frontend/src/styles.css` (`.row-actions`, `.status-pill.verified`) e non toccano altri componenti.

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint` + `make fe-lint`
- **Types:** `make types`
- **Test subset:** `make test` + `make fe-test`
- **Regression guard:** tutti i T-ID del piano (I-1..I-4), in particolare `unread_count` invariato dopo toggle verified e `bulk-read` che non tocca verified.

## Phase done criterion

Tutte le gate verdi, spec aggiornata, check manuale 1-6 passato. La feature e' completa: toggle read/unread e verified/not-verified su elenco e dettaglio, stile consistente, zero regressioni.