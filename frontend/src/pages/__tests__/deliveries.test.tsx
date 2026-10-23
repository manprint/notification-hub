import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import DeliveriesPage from "../DeliveriesPage";
import { setRefreshToken } from "../../api/client";
import { fixtureDeliveries } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

describe("DeliveriesPage", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture"); // fixtureMe di default ha ruolo owner
  });

  it("T-UI17 test_retry_solo_su_dead: il pulsante compare solo sulle righe dead", async () => {
    renderWithProviders(<DeliveriesPage />);

    await waitFor(() => {
      expect(screen.getByText("Morta")).toBeInTheDocument();
    });

    const rows = screen.getAllByRole("row").slice(1); // salta l'intestazione
    const retryButtons = screen.queryAllByRole("button", { name: "Ri-accoda" });
    expect(retryButtons).toHaveLength(1);

    const deadRow = rows.find((row) => row.textContent?.includes("Morta"));
    const sentRow = rows.find((row) => row.textContent?.includes("Inviata"));
    expect(deadRow?.querySelector("button")).not.toBeNull();
    expect(sentRow?.querySelector("button")).toBeNull();
  });
});

describe("DeliveriesPage leggibilità", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  it("ogni riga dice quale notifica è stata inoltrata e verso quale canale", async () => {
    renderWithProviders(<DeliveriesPage />);

    await waitFor(() => {
      expect(screen.getByText("Morta")).toBeInTheDocument();
    });

    // canale di destinazione e receiver di origine, non solo id opachi
    expect(screen.getAllByText("Slack #ops").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Backup notturno/).length).toBeGreaterThan(0);

    // si arriva alla notifica inoltrata, senza leggerne il corpo qui
    const apri = screen.getAllByRole("link", { name: "Apri" });
    expect(apri[0]).toHaveAttribute("href", "/notifications/n1");
  });

  it("non stampa il corpo del messaggio nella tabella: c'è un link «Apri»", async () => {
    const lungo = "Backup FALLITO: " + "disco pieno su /var ".repeat(40);
    server.use(
      http.get("/api/v1/deliveries", () =>
        HttpResponse.json({
          deliveries: [{ ...fixtureDeliveries[0], content_preview: lungo }],
          next_cursor: null,
        }),
      ),
    );

    renderWithProviders(<DeliveriesPage />);
    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );

    // Il corpo si legge nella notifica: una preview lunga qui sfonda la riga e
    // spinge fuori vista le colonne che dicono com'è andata la consegna.
    expect(screen.queryByText(/disco pieno su \/var/)).not.toBeInTheDocument();
    const riga = screen.getAllByRole("row")[1];
    expect(within(riga).getByRole("link", { name: "Apri" })).toHaveAttribute(
      "href",
      "/notifications/n1",
    );
  });

  it("la riga resta riconoscibile senza il testo: severity, receiver, quando", async () => {
    renderWithProviders(<DeliveriesPage />);
    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );

    const riga = screen.getAllByRole("row")[1];
    expect(within(riga).getByText("Errore")).toBeInTheDocument();
    expect(within(riga).getByText("da Backup notturno")).toBeInTheDocument();
    // La data formattata come nel resto dell'applicazione, non l'ISO grezzo.
    expect(within(riga).getByText("01/08/2026")).toBeInTheDocument();
  });

  it("la severity sta in una colonna sua, come nell'elenco delle notifiche", async () => {
    renderWithProviders(<DeliveriesPage />);
    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );

    const intestazioni = within(screen.getAllByRole("row")[0])
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(intestazioni.slice(0, 2)).toEqual(["Severity", "Notifica inoltrata"]);

    const celle = within(screen.getAllByRole("row")[1]).getAllByRole("cell");
    // Il badge sta nella prima cella e non dentro il testo di un'altra: le
    // severity si scorrono in verticale.
    expect(within(celle[0]).getByText("Errore")).toBeInTheDocument();
    expect(within(celle[1]).queryByText("Errore")).not.toBeInTheDocument();
    expect(within(celle[1]).getByRole("link", { name: "Apri" })).toBeInTheDocument();
  });

  it("la data di ricezione ha la colonna «Ricevuta», con giorno e ora su due righe", async () => {
    renderWithProviders(<DeliveriesPage />);
    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );

    const intestazioni = within(screen.getAllByRole("row")[0])
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    const colonna = intestazioni.indexOf("Ricevuta");
    expect(colonna).toBeGreaterThan(-1);

    const cella = within(screen.getAllByRole("row")[1]).getAllByRole("cell")[colonna];
    expect(within(cella).getByText("01/08/2026")).toBeInTheDocument();
    expect(within(cella).getByText(/^0\d:00:00$/)).toBeInTheDocument();
  });
});

describe("DeliveriesPage filtri", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  it("gli stati della tendina usano le stesse parole della tabella", async () => {
    renderWithProviders(<DeliveriesPage />);
    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );

    const tendina = screen.getByLabelText("Stato della consegna");
    const opzioni = within(tendina)
      .getAllByRole("option")
      .map((o) => o.textContent);
    // Non gli identificativi dell'API ("dead", "sent"): la tabella dice
    // "Morta" e "Inviata", il filtro deve dire lo stesso.
    expect(opzioni).toContain("Morta");
    expect(opzioni).toContain("Inviata");
    expect(opzioni).not.toContain("dead");
  });

  it("con un filtro attivo compare il modo di azzerarlo", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DeliveriesPage />);
    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );

    expect(screen.queryByRole("button", { name: /Azzera i filtri/ })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Stato della consegna"), "dead");
    const azzera = await screen.findByRole("button", { name: "Azzera i filtri (1)" });

    await user.click(azzera);
    expect(screen.getByLabelText("Stato della consegna")).toHaveValue("");
    expect(screen.queryByRole("button", { name: /Azzera i filtri/ })).not.toBeInTheDocument();
  });
});

describe("DeliveriesPage paginazione", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  // Contratto C2: la lista nuda si fermava alle prime righe senza dirlo; ora e'
  // una pagina a cursore, e il cursore si ripassa cosi' com'e'.
  it("«Carica altri» ripassa il cursore opaco e accoda la pagina successiva", async () => {
    const richieste: URLSearchParams[] = [];
    server.use(
      http.get("/api/v1/deliveries", ({ request }) => {
        const params = new URL(request.url).searchParams;
        richieste.push(params);
        if (params.get("cursor") === "opaco==") {
          return HttpResponse.json({ deliveries: [fixtureDeliveries[1]], next_cursor: null });
        }
        return HttpResponse.json({ deliveries: [fixtureDeliveries[0]], next_cursor: "opaco==" });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<DeliveriesPage />);

    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );
    expect(screen.queryByText("Inviata", { selector: ".status-pill" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Carica altri" }));

    expect(await screen.findByText("Inviata", { selector: ".status-pill" })).toBeInTheDocument();
    // La prima pagina resta: la seconda si accoda.
    expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument();
    expect(richieste[0].get("cursor")).toBeNull();
    expect(richieste[0].get("limit")).toBe("100");
    expect(richieste[1].get("cursor")).toBe("opaco==");
    expect(screen.queryByRole("button", { name: "Carica altri" })).not.toBeInTheDocument();
  });

  it("cambiare un filtro riparte dalla prima pagina", async () => {
    const richieste: URLSearchParams[] = [];
    server.use(
      http.get("/api/v1/deliveries", ({ request }) => {
        const params = new URL(request.url).searchParams;
        richieste.push(params);
        if (params.get("cursor")) {
          return HttpResponse.json({ deliveries: [fixtureDeliveries[1]], next_cursor: null });
        }
        return HttpResponse.json({ deliveries: [fixtureDeliveries[0]], next_cursor: "opaco==" });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<DeliveriesPage />);

    await user.click(await screen.findByRole("button", { name: "Carica altri" }));
    await screen.findByText("Inviata", { selector: ".status-pill" });

    await user.selectOptions(screen.getByLabelText("Stato della consegna"), "dead");

    await waitFor(() => expect(richieste[richieste.length - 1]?.get("status")).toBe("dead"));
    // Il cursore della vista precedente non vale per il nuovo filtro.
    expect(richieste[richieste.length - 1]?.get("cursor")).toBeNull();
    await waitFor(() =>
      expect(screen.queryByText("Inviata", { selector: ".status-pill" })).not.toBeInTheDocument(),
    );
  });
});

describe("DeliveriesPage prossimo tentativo", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  function rigaCon(stato: string): HTMLElement {
    const riga = screen
      .getAllByRole("row")
      .find((r) => within(r).queryByText(stato, { selector: ".status-pill" }) !== null);
    if (!riga) throw new Error(`Nessuna riga in stato ${stato}`);
    return riga;
  }

  it("compare solo per le consegne che aspettano un nuovo tentativo", async () => {
    server.use(
      http.get("/api/v1/deliveries", () =>
        HttpResponse.json({
          deliveries: [
            { ...fixtureDeliveries[0], id: "dd", status: "dead" },
            { ...fixtureDeliveries[0], id: "ds", status: "sending", attempts: 1 },
            { ...fixtureDeliveries[0], id: "dp", status: "pending", attempts: 0 },
            { ...fixtureDeliveries[0], id: "df", status: "failed", attempts: 2 },
          ],
          next_cursor: null,
        }),
      ),
    );
    renderWithProviders(<DeliveriesPage />);
    await waitFor(() => expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument());

    // Una consegna morta non ritenta piu' da sola, una in invio lo sta gia'
    // facendo: per loro next_attempt_at non e' un appuntamento.
    expect(within(rigaCon("Morta")).queryByText(/prossimo tentativo/)).not.toBeInTheDocument();
    expect(within(rigaCon("In invio")).queryByText(/prossimo tentativo/)).not.toBeInTheDocument();
    expect(within(rigaCon("In attesa")).getByText(/prossimo tentativo/)).toBeInTheDocument();
    expect(within(rigaCon("Fallita")).getByText(/prossimo tentativo/)).toBeInTheDocument();
  });

  it("uno stato che la dashboard non conosce resta leggibile", async () => {
    server.use(
      http.get("/api/v1/deliveries", () =>
        HttpResponse.json({
          deliveries: [{ ...fixtureDeliveries[0], status: "archived" }],
          next_cursor: null,
        }),
      ),
    );
    renderWithProviders(<DeliveriesPage />);

    expect(await screen.findByText("archived", { selector: ".status-pill" })).toBeInTheDocument();
    expect(screen.getByText(/stato non riconosciuto/)).toBeInTheDocument();
  });
});

describe("DeliveriesPage filtro canale del viewer", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: "u9",
          email: "viewer@acme.test",
          role: "viewer",
          tenant_id: "t1",
          tenant_name: "ACME",
        }),
      ),
    );
  });

  afterEach(() => {
    server.events.removeAllListeners();
  });

  it("il viewer filtra per canale senza chiedere /api/v1/channels", async () => {
    let richiesteCanali = 0;
    server.events.on("request:start", ({ request }) => {
      if (new URL(request.url).pathname === "/api/v1/channels") richiesteCanali++;
    });

    renderWithProviders(<DeliveriesPage />);
    await waitFor(() =>
      expect(screen.getByText("Morta", { selector: ".status-pill" })).toBeInTheDocument(),
    );

    const tendina = screen.getByLabelText("Canale", { selector: "select" });
    expect(within(tendina).getByRole("option", { name: "Slack #ops" })).toBeInTheDocument();
    expect(richiesteCanali).toBe(0);
  });

  it("il canale già filtrato resta nella tendina anche senza consegne", async () => {
    server.use(
      http.get("/api/v1/deliveries", () => HttpResponse.json({ deliveries: [], next_cursor: null })),
    );

    renderWithProviders(<DeliveriesPage />, ["/deliveries?channel_id=c9"]);
    const tendina = await screen.findByLabelText("Canale", { selector: "select" });

    expect(tendina).toHaveValue("c9");
    expect(within(tendina).getByRole("option", { name: "Canale selezionato" })).toBeInTheDocument();
  });
});
