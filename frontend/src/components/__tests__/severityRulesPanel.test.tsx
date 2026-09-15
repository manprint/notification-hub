import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import SeverityRulesPanel from "../SeverityRulesPanel";
import { setRefreshToken } from "../../api/client";
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
    expect(within(riga).getByText("cambia")).toBeInTheDocument();
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
    expect(screen.queryByRole("button", { name: "Modifica" })).not.toBeInTheDocument();
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

    await user.type(await screen.findByLabelText("Pattern RE2"), "PANIC");
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

    await user.type(await screen.findByLabelText("Pattern RE2"), "(aperta");
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
});
