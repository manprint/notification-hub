import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import SeverityRulesPanel from "../SeverityRulesPanel";
import { setRefreshToken } from "../../api/client";
import { fixtureSeverityChain, fixtureSeverityReplay } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "../../pages/__tests__/testUtils";
import type { ReceiverOut, SeverityRuleOut } from "../../api/types";

const receiver: ReceiverOut = {
  id: "r1",
  group_id: "g1",
  slug: "maritime-backup-notturno-Kj8mQ2xN7vB4pR9wLs3tYc",
  ingest_url:
    "https://notifyhub.example.com/ingest/maritime-backup-notturno-Kj8mQ2xN7vB4pR9wLs3tYc",
  name: "Backup notturno",
  status: "active",
  ingestion_module: "http_raw",
  default_severity: "info",
  exit_code_severity: "critical",
  duration_threshold_seconds: 600,
  duration_severity: "error",
  max_body_bytes: 1_048_576,
  rate_limit_per_min: 60,
  expected_every_seconds: null,
  expected_cron: null,
  expected_timezone: null,
  expected_grace_seconds: null,
  missing_severity: null,
  last_notification_at: null,
  last_start_at: null,
  missing_alerted_at: null,
  expected_since: null,
  expected_deadline_at: null,
  expected_late: false,
};

const twoRules: SeverityRuleOut[] = [
  {
    id: "sr1",
    receiver_id: "r1",
    priority: 10,
    pattern: "ERRORE",
    case_insensitive: true,
    severity: "error",
    enabled: true,
  },
  {
    id: "sr2",
    receiver_id: "r1",
    priority: 20,
    pattern: "attenzione",
    case_insensitive: false,
    severity: "warning",
    enabled: false,
  },
];

function renderPanel(rules: SeverityRuleOut[] = twoRules, override: Partial<ReceiverOut> = {}) {
  server.use(http.get("/api/v1/receivers/r1/severity-rules", () => HttpResponse.json(rules)));
  return renderWithProviders(<SeverityRulesPanel receiver={{ ...receiver, ...override }} />);
}

describe("SeverityRulesPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture"); // fixtureMe di default ha ruolo owner
  });

  it("riassume la catena con la configurazione reale del receiver", async () => {
    renderPanel();

    const chain = await screen.findByRole("list");
    const passi = within(chain).getAllByRole("listitem");
    expect(passi).toHaveLength(5);
    expect(passi[0].textContent).toContain("Severity esplicita");
    expect(passi[1].textContent).toContain("Exit code diverso da zero");
    expect(passi[2].textContent).toContain("Durata oltre la soglia");
    expect(passi[2].textContent).toContain("10m00s");
    expect(passi[3].textContent).toContain("1 attiva"); // la seconda e' disattivata
    expect(passi[3].textContent).toContain("preset applicati");
    expect(passi[4].textContent).toContain("Default del receiver");
  });

  it("dice che la durata non ha effetto quando non c'e' soglia", async () => {
    renderPanel(twoRules, { duration_threshold_seconds: null, duration_severity: null });

    const chain = await screen.findByRole("list");
    const passi = within(chain).getAllByRole("listitem");
    expect(passi[2].textContent).toContain("nessuna soglia su questo receiver");
  });

  it("dice che l'exit code non ha effetto quando la politica e' disattivata", async () => {
    renderPanel(twoRules, { exit_code_severity: null });

    const chain = await screen.findByRole("list");
    const passi = within(chain).getAllByRole("listitem");
    expect(passi[1].textContent).toContain("nessun effetto");
  });

  it("mostra stato e sensibilita alle maiuscole di ogni regola", async () => {
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    const riga = screen.getByText("attenzione").closest("tr")!;
    expect(within(riga).getByText("distinte")).toBeInTheDocument();
    expect(within(riga).getByLabelText("Attiva attenzione")).not.toBeChecked();
  });

  it("segna quale regola viene valutata per prima", async () => {
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    const riga = screen.getByText("ERRORE").closest("tr")!;
    expect(within(riga).getByText("valutata per prima")).toBeInTheDocument();
  });

  it("le frecce inviano il nuovo ordine completo al backend", async () => {
    const user = userEvent.setup();
    let inviato: unknown = null;
    server.use(
      http.put("/api/v1/receivers/r1/severity-rules/order", async ({ request }) => {
        inviato = await request.json();
        return HttpResponse.json([]);
      }),
    );
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    await user.click(screen.getByLabelText("Sposta giù ERRORE"));

    await waitFor(() => expect(inviato).toEqual({ rule_ids: ["sr2", "sr1"] }));
  });

  it("T-ORD1 le frecce restano ferme finche' un riordino e' in volo", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    let sblocca: () => void = () => undefined;
    server.use(
      http.put("/api/v1/receivers/r1/severity-rules/order", async () => {
        chiamate += 1;
        await new Promise<void>((resolve) => {
          sblocca = resolve;
        });
        return HttpResponse.json([]);
      }),
    );
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    await user.click(screen.getByLabelText("Sposta giù ERRORE"));
    await waitFor(() => expect(chiamate).toBe(1));

    // Un secondo click adesso calcolerebbe l'ordine da quello vecchio e
    // annullerebbe il primo spostamento.
    expect(screen.getByLabelText("Sposta su attenzione")).toBeDisabled();
    expect(screen.getByLabelText("Sposta giù ERRORE")).toBeDisabled();
    await user.click(screen.getByLabelText("Sposta su attenzione"));

    sblocca();
    await waitFor(() => expect(screen.getByLabelText("Sposta giù ERRORE")).toBeEnabled());
    expect(chiamate).toBe(1);
  });

  it("T-REP1 dopo una nuova regola la prova sulle ultime notifiche si ricalcola", async () => {
    const user = userEvent.setup();
    let ricalcoli = 0;
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules/replay", () => {
        ricalcoli += 1;
        return HttpResponse.json(fixtureSeverityReplay);
      }),
      http.post("/api/v1/receivers/r1/severity-rules", () =>
        HttpResponse.json({ ...twoRules[0], id: "sr3", pattern: "PANIC" }, { status: 201 }),
      ),
    );
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /ultime notifiche/i }));
    await waitFor(() => expect(ricalcoli).toBe(1));

    await user.type(screen.getByLabelText("Pattern"), "PANIC");
    await user.click(screen.getByRole("button", { name: "Aggiungi regola" }));

    await waitFor(() => expect(ricalcoli).toBe(2));
  });

  it("T-CHAIN1 mentre la catena effettiva carica non dice 'nessuna regola attiva'", async () => {
    let rispondi: () => void = () => undefined;
    server.use(
      http.get("/api/v1/receivers/r1/severity-chain", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json(fixtureSeverityChain);
      }),
    );
    renderPanel();

    expect(await screen.findByText(/Caricamento della catena/)).toBeInTheDocument();
    expect(screen.queryByText(/Nessuna regola attiva/)).not.toBeInTheDocument();

    rispondi();
    await waitFor(() =>
      expect(screen.queryByText(/Caricamento della catena/)).not.toBeInTheDocument(),
    );
  });

  it("la prima regola non si puo spostare piu in su", async () => {
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    expect(screen.getByLabelText("Sposta su ERRORE")).toBeDisabled();
    expect(screen.getByLabelText("Sposta giù attenzione")).toBeDisabled();
  });

  it("il replay mostra quali notifiche cambierebbero severity", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole("button", { name: /ultime notifiche/i }));

    await waitFor(() => {
      expect(screen.getByText(/1 delle ultime 2 notifiche/)).toBeInTheDocument();
    });
    const riga = screen.getByText(/Backup FALLITO/).closest("tr")!;
    expect(within(riga).getByText("Cambia")).toBeInTheDocument();
  });

  it("il member vede le regole ma il viewer non puo modificarle", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: "u1",
          email: "viewer@acme.test",
          role: "viewer",
          tenant_id: "t1",
          tenant_name: "ACME",
        }),
      ),
    );
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /^Modifica/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Sposta giù ERRORE")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aggiungi regola" })).not.toBeInTheDocument();
  });

  it("la nuova regola non chiede la priorita: la assegna il backend", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/receivers/r1/severity-rules", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...twoRules[0], id: "sr3" }, { status: 201 });
      }),
    );
    renderPanel();

    await user.type(await screen.findByLabelText("Pattern"), "PANIC");
    await user.click(screen.getByRole("button", { name: "Aggiungi regola" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).not.toHaveProperty("priority");
    expect(inviato).toMatchObject({ pattern: "PANIC", case_insensitive: true });
  });

  it("mostra l'errore RE2 restituito dal backend", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/receivers/r1/severity-rules", () =>
        HttpResponse.json(
          {
            type: "/problems/validation-error",
            title: "Validation Error",
            status: 422,
            detail: "Pattern not compilable by RE2: missing ): (aperta",
          },
          { status: 422 },
        ),
      ),
    );
    renderPanel();

    await user.type(await screen.findByLabelText("Pattern"), "(aperta");
    await user.click(screen.getByRole("button", { name: "Aggiungi regola" }));

    await waitFor(() => {
      // Due volte: l'avviso immediato e il banner che resta dentro il modulo.
      expect(screen.getAllByText(/not compilable by RE2/).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("la prova severity accetta un exit code simulato", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/receivers/r1/test-severity", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          severity: "critical",
          source: "exit_code",
          matched_rule_id: null,
          matched_pattern: null,
        });
      }),
    );
    renderPanel();

    await user.type(await screen.findByLabelText(/contenuto di prova/i), "qualcosa");
    await user.type(screen.getByLabelText(/exit code simulato/i), "3");
    await user.click(screen.getByRole("button", { name: "Esegui prova" }));

    await waitFor(() => expect(inviato).toMatchObject({ content: "qualcosa", exit_code: 3 }));
    expect(screen.getByText(/decisa da/).textContent).toContain("exit code");
  });

  it("T-RULES1 mentre le regole caricano o non si leggono non dice 'nessuna regola'", async () => {
    let rispondi: () => void = () => undefined;
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<SeverityRulesPanel receiver={receiver} />);

    expect(await screen.findByText(/Caricamento delle regole/)).toBeInTheDocument();
    expect(screen.queryByText(/Nessuna regola:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/nessuna attiva/)).not.toBeInTheDocument();

    rispondi();
    expect(await screen.findByText(/Nessuna regola:/)).toBeInTheDocument();
  });

  it("T-RULES2 se le regole non si leggono la tabella non dice 'nessuna regola'", async () => {
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules", () =>
        HttpResponse.json(
          { type: "/problems/internal", title: "Internal", status: 500, detail: "Boom." },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<SeverityRulesPanel receiver={receiver} />);

    expect(await screen.findByText(/Boom/)).toBeInTheDocument();
    expect(screen.queryByText(/Nessuna regola:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/nessuna attiva/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Caricamento delle regole/)).not.toBeInTheDocument();
  });

  it("T-PROVA1 la prova severity non parte con il contenuto vuoto", async () => {
    const user = userEvent.setup();
    const inviati: unknown[] = [];
    server.use(
      http.post("/api/v1/receivers/r1/test-severity", async ({ request }) => {
        inviati.push(await request.json());
        return HttpResponse.json({ severity: "info", source: "default" });
      }),
    );
    renderPanel();

    await user.click(await screen.findByRole("button", { name: "Esegui prova" }));

    expect(await screen.findByText("Scrivi il testo di prova.")).toBeInTheDocument();
    expect(screen.getByLabelText(/contenuto di prova/i)).toHaveAttribute("aria-invalid", "true");
    expect(inviati).toHaveLength(0);
  });

  it("T-PROVA2 una durata che non sta nei secondi del backend non si perde in silenzio", async () => {
    const user = userEvent.setup();
    const inviati: unknown[] = [];
    server.use(
      http.post("/api/v1/receivers/r1/test-severity", async ({ request }) => {
        inviati.push(await request.json());
        return HttpResponse.json({ severity: "info", source: "default" });
      }),
    );
    renderPanel();

    await user.type(await screen.findByLabelText(/contenuto di prova/i), "qualcosa");
    await user.type(screen.getByLabelText(/durata simulata/i), "1e308");
    await user.click(screen.getByRole("button", { name: "Esegui prova" }));

    expect(await screen.findByText(/Troppo grande/)).toBeInTheDocument();
    expect(inviati).toHaveLength(0);
  });
  it("T-ORD2 dopo un riordino rifiutato la lista si rilegge prima della mossa successiva", async () => {
    const user = userEvent.setup();
    let letture = 0;
    const ordini: string[] = [];
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules", () => {
        letture += 1;
        return HttpResponse.json(twoRules);
      }),
      http.put("/api/v1/receivers/r1/severity-rules/order", async ({ request }) => {
        const body = (await request.json()) as { rule_ids: string[] };
        ordini.push(body.rule_ids.join(","));
        return HttpResponse.json(
          { type: "/problems/unprocessable", title: "Unprocessable", status: 422, detail: "No." },
          { status: 422 },
        );
      }),
    );
    renderWithProviders(<SeverityRulesPanel receiver={receiver} />);

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    const lettureIniziali = letture;
    await user.click(screen.getByLabelText("Sposta giù ERRORE"));

    await waitFor(() => expect(ordini).toHaveLength(1));
    // Il rifiuto ha fatto rileggere le regole: la cache non è più quella di prima.
    await waitFor(() => expect(letture).toBeGreaterThan(lettureIniziali));
  });

  it("T-RULE1 una regola senza pattern dice il problema sul campo, senza la validazione del browser", async () => {
    const user = userEvent.setup();
    const inviati: unknown[] = [];
    server.use(
      http.post("/api/v1/receivers/r1/severity-rules", async ({ request }) => {
        inviati.push(await request.json());
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Aggiungi regola" }));

    const messaggio = await screen.findByText("Il pattern è obbligatorio.");
    const campo = screen.getByLabelText("Pattern");
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(campo).toHaveAttribute("aria-describedby", messaggio.id);
    expect(inviati).toHaveLength(0);
  });

  it("T-RULES3 se la rilettura fallisce su una lista vuota non dice 'nessuna regola'", async () => {
    const user = userEvent.setup();
    let fallisci = false;
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules", () =>
        fallisci
          ? HttpResponse.json(
              { type: "/problems/internal", title: "Internal", status: 500, detail: "Rilettura fallita." },
              { status: 500 },
            )
          : HttpResponse.json([]),
      ),
      http.post("/api/v1/receivers/r1/severity-rules", () => {
        fallisci = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderWithProviders(<SeverityRulesPanel receiver={receiver} />);

    expect(await screen.findByText(/Nessuna regola:/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Pattern"), "NUOVA");
    await user.click(screen.getByRole("button", { name: "Aggiungi regola" }));

    // La rilettura dopo l'aggiunta fallisce: la lista vuota in cache non è più una
    // risposta, quindi né «nessuna regola» né «nessuna attiva» vanno detti.
    expect(await screen.findByText(/Rilettura fallita/)).toBeInTheDocument();
    expect(screen.queryByText(/Nessuna regola:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/nessuna attiva/)).not.toBeInTheDocument();
  });

  it("T-LABEL1 le severity delle regole hanno le etichette italiane, come nelle tabelle", async () => {
    renderPanel([]);

    const tendina = await screen.findByLabelText("Severity", { selector: "select" });
    expect(within(tendina).getByRole("option", { name: "Critica" })).toHaveAttribute(
      "value",
      "critical",
    );
    expect(within(tendina).queryByRole("option", { name: "critical" })).toBeNull();
    // Il receiver di questa prova ha severity di default «info».
    expect(await screen.findByText(/Nessuna regola:.*\(Info\)/)).toBeInTheDocument();
  });

  it("T-ACT1 ogni regola ha pulsanti con il suo nome, e l'intestazione Azioni c'è anche se nascosta", async () => {
    renderPanel();

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Modifica la regola ERRORE" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Elimina la regola attenzione" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Azioni" })).toBeInTheDocument();
  });

  it("T-ORD2 il riordino parte dall'ordine letto adesso sul server, non da quello in cache", async () => {
    const user = userEvent.setup();
    let letture = 0;
    let inviato: string[] | null = null;
    const terza: SeverityRuleOut = {
      id: "sr3",
      receiver_id: "r1",
      priority: 30,
      pattern: "avviso",
      case_insensitive: true,
      severity: "info",
      enabled: true,
    };
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules", () => {
        letture += 1;
        // Dalla prima lettura in poi qualcun altro ha messo una regola in cima.
        return HttpResponse.json(letture === 1 ? twoRules : [terza, twoRules[0], twoRules[1]]);
      }),
      http.put("/api/v1/receivers/r1/severity-rules/order", async ({ request }) => {
        inviato = ((await request.json()) as { rule_ids: string[] }).rule_ids;
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<SeverityRulesPanel receiver={receiver} />);

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    await user.click(screen.getByLabelText("Sposta giù ERRORE"));

    // In cache ERRORE sta in cima; letto adesso sta in mezzo e scende di uno, prima
    // di attenzione.
    await waitFor(() => expect(inviato).toEqual(["sr3", "sr2", "sr1"]));
  });

  it("T-ORD3 se la lettura fresca fallisce il riordino non parte e il motivo si vede", async () => {
    const user = userEvent.setup();
    let letture = 0;
    let ordini = 0;
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules", () => {
        letture += 1;
        return letture === 1
          ? HttpResponse.json(twoRules)
          : HttpResponse.json(
              { type: "/problems/internal", title: "Internal", status: 500, detail: "Lettura fallita." },
              { status: 500 },
            );
      }),
      http.put("/api/v1/receivers/r1/severity-rules/order", () => {
        ordini += 1;
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<SeverityRulesPanel receiver={receiver} />);

    await waitFor(() => expect(screen.getByText("ERRORE")).toBeInTheDocument());
    await user.click(screen.getByLabelText("Sposta giù ERRORE"));

    expect((await screen.findAllByText(/Lettura fallita/)).length).toBeGreaterThan(0);
    expect(ordini).toBe(0);
  });
});
