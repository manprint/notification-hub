import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import AuditNotificationStatusPage from "../AuditNotificationStatusPage";
import AuditPage from "../AuditPage";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

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
    expect(screen.getByText("Backup notturno fallito")).toBeInTheDocument();
  });

  it("il filtro per id notifica viene passato all'API", async () => {
    const urls: string[] = [];
    server.use(
      http.get("/api/v1/audit/notification-status", ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ events: [], next_cursor: null });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<AuditNotificationStatusPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/id notifica/i)).toBeInTheDocument();
    });
    await user.type(screen.getByLabelText(/id notifica/i), "n1");

    await waitFor(() => {
      expect(urls.some((url) => url.includes("notification_id=n1"))).toBe(true);
    });
  });
});
