import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import NotificationsPage from "../NotificationsPage";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

describe("NotificationsPage", () => {
  it("T-UI7 test_carica_altri_usa_il_cursore: il secondo caricamento usa next_cursor e accoda senza duplicati", async () => {
    renderWithProviders(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Backup FALLITO/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Terza notifica/)).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Carica altri" }));

    await waitFor(() => {
      expect(screen.getByText(/Terza notifica/)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Backup FALLITO/)).toHaveLength(1);
  });

  it("T-UI8 test_nota_sulla_ricerca_presente: mostra la nota sui 4096 caratteri", async () => {
    renderWithProviders(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Backup FALLITO/)).toBeInTheDocument();
    });

    expect(
      screen.getByText("La ricerca esamina i primi 4096 caratteri del contenuto."),
    ).toBeInTheDocument();
  });

  it("T-UI9 test_filtri_nella_query: gruppo e severity minima selezionati compaiono nella richiesta", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 });
      }),
    );

    renderWithProviders(<NotificationsPage />);

    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Server Produzione" })).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByDisplayValue("Tutti i gruppi"), "g1");
    await user.selectOptions(screen.getByDisplayValue("Qualsiasi severity"), "error");

    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("group_id")).toBe("g1");
      expect(capturedUrl?.searchParams.get("severity_min")).toBe("error");
    });
  });
});
