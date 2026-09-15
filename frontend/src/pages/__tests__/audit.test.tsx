import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import AuditNotificationStatusPage from "../AuditNotificationStatusPage";
import AuditPage from "../AuditPage";
import { fixtureAuditEvents } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

/** Indice di una colonna per intestazione: le colonne cambiano, i test che le
 *  contano a mano no. */
function colonna(titolo: string): number {
  return within(screen.getAllByRole("row")[0])
    .getAllByRole("columnheader")
    .findIndex((h) => h.textContent === titolo);
}

function cella(riga: number, titolo: string): HTMLElement {
  return within(screen.getAllByRole("row")[riga]).getAllByRole("cell")[colonna(titolo)];
}

describe("AuditPage", () => {
  it("mostra chi ha fatto cosa, con il diff dei campi cambiati", async () => {
    renderWithProviders(<AuditPage />);

    await waitFor(() => {
      expect(screen.getByText("mario@acme.test")).toBeInTheDocument();
    });
    expect(screen.getByText("Segnata come verificata")).toBeInTheDocument();
    expect(screen.getByText("verified: no → sì")).toBeInTheDocument();
    expect(screen.getByText("Backup notturno fallito")).toBeInTheDocument();
  });

  it("ogni riga dice in quale gruppo e su quale receiver è avvenuta", async () => {
    renderWithProviders(<AuditPage />);
    await waitFor(() => expect(screen.getByText("mario@acme.test")).toBeInTheDocument());

    // Senza, "receiver / Backup notturno" non identifica niente: lo stesso
    // nome puo' stare in tre gruppi diversi.
    const posizione = cella(1, "Gruppo / Receiver");
    const link = within(posizione).getByRole("link", { name: "Backup notturno" });
    expect(link).toHaveAttribute("href", "/receivers/r1");
    expect(within(posizione).getByText("Server Produzione")).toBeInTheDocument();
  });

  it("se la risorsa è stata cancellata la posizione è un trattino, non un'invenzione", async () => {
    server.use(
      http.get("/api/v1/audit/events", () =>
        HttpResponse.json({
          events: [
            {
              ...fixtureAuditEvents[0],
              resource_type: "receiver",
              group_id: null,
              group_name: null,
              receiver_id: null,
              receiver_name: null,
            },
          ],
          next_cursor: null,
        }),
      ),
    );

    renderWithProviders(<AuditPage />);
    await waitFor(() => expect(screen.getByText("mario@acme.test")).toBeInTheDocument());

    // La riga di audit sopravvive alla risorsa: il nome congelato resta, la
    // posizione no.
    expect(cella(1, "Gruppo / Receiver").textContent).toBe("—");
    expect(screen.getByText("Backup notturno fallito")).toBeInTheDocument();
  });

  it("i filtri finiscono nella query dell'API", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/v1/audit/events", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ events: [], next_cursor: null });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AuditPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/esito/i)).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText(/esito/i), "failure");

    await waitFor(() => {
      expect(urls.some((url) => url.includes("outcome=failure"))).toBe(true);
    });
  });
});

describe("AuditNotificationStatusPage", () => {
  it("un bulk-read si legge come operazione in blocco, non come una notifica sola", async () => {
    renderWithProviders(<AuditNotificationStatusPage />);

    // "operazione in blocco" e' testo di riga: attenderlo evita di scambiare
    // per un risultato l'omonima voce della tendina dei filtri.
    expect(await screen.findByText("operazione in blocco")).toBeInTheDocument();
    expect(screen.getByText("12 notifiche")).toBeInTheDocument();
  });

  it("il contenuto sta dietro «Apri», non stampato in tabella", async () => {
    renderWithProviders(<AuditNotificationStatusPage />);
    await screen.findByText("operazione in blocco");

    expect(screen.queryByText("Backup notturno fallito")).not.toBeInTheDocument();
    expect(within(cella(1, "Notifica")).getByRole("link", { name: "Apri" })).toHaveAttribute(
      "href",
      "/notifications/n1",
    );
  });

  it("dice su quale gruppo e receiver, anche per l'operazione in blocco", async () => {
    renderWithProviders(<AuditNotificationStatusPage />);
    await screen.findByText("operazione in blocco");

    // Il bulk-read non ha una notifica sola: l'ambito e' quello dei filtri con
    // cui e' partito, e il backend lo risolve allo stesso modo.
    const posizione = cella(2, "Gruppo / Receiver");
    expect(within(posizione).getByRole("link", { name: "Backup notturno" })).toBeInTheDocument();
    expect(within(posizione).getByText("Server Produzione")).toBeInTheDocument();
  });

  it("non si cerca più per id: il filtro arriva dall'URL e si toglie", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/v1/audit/notification-status", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ events: fixtureAuditEvents, next_cursor: null });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AuditNotificationStatusPage />, [
      "/settings/letture-e-verifiche?notification_id=n1",
    ]);

    // Gli uuid non sono esposti da nessuna parte nell'interfaccia: un campo in
    // cui incollarli era una ricerca senza sorgente.
    await waitFor(() => expect(screen.queryByLabelText(/id notifica/i)).not.toBeInTheDocument());
    await waitFor(() => expect(urls.some((url) => url.includes("notification_id=n1"))).toBe(true));
    // La vista filtrata si dichiara e si lascia.
    expect(screen.getByText(/Storico di una sola notifica/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Apri la notifica" })).toHaveAttribute(
      "href",
      "/notifications/n1",
    );

    await user.click(screen.getByRole("button", { name: "Mostrale tutte" }));
    await waitFor(() => expect(screen.queryByText(/Storico di una sola notifica/)).toBeNull());
    expect(urls.some((url) => !url.includes("notification_id"))).toBe(true);
  });
});
