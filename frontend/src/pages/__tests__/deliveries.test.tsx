import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
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
        HttpResponse.json([{ ...fixtureDeliveries[0], content_preview: lungo }]),
      ),
    );

    renderWithProviders(<DeliveriesPage />);
    await waitFor(() => expect(screen.getByText("Morta")).toBeInTheDocument());

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
    await waitFor(() => expect(screen.getByText("Morta")).toBeInTheDocument());

    const riga = screen.getAllByRole("row")[1];
    expect(within(riga).getByText("Errore")).toBeInTheDocument();
    expect(within(riga).getByText(/da Backup notturno/)).toBeInTheDocument();
    // La data formattata come nel resto dell'applicazione, non l'ISO grezzo
    // (compare anche nella colonna dei tentativi: qui conta quella di origine).
    expect(within(riga).getByText(/da Backup notturno · 01\/08\/2026/)).toBeInTheDocument();
  });
});

describe("DeliveriesPage filtri", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  it("gli stati della tendina usano le stesse parole della tabella", async () => {
    renderWithProviders(<DeliveriesPage />);
    await waitFor(() => expect(screen.getByText("Morta")).toBeInTheDocument());

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
    await waitFor(() => expect(screen.getByText("Morta")).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: /Azzera i filtri/ })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Stato della consegna"), "dead");
    const azzera = await screen.findByRole("button", { name: "Azzera i filtri (1)" });

    await user.click(azzera);
    expect(screen.getByLabelText("Stato della consegna")).toHaveValue("");
    expect(screen.queryByRole("button", { name: /Azzera i filtri/ })).not.toBeInTheDocument();
  });
});
