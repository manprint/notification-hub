import { screen, waitFor, within } from "@testing-library/react";
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

  it("mostra l'origine di ogni notifica, sorveglianza compresa", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "nm1",
              receiver_id: "r1",
              content_preview: "[notifyhub] nessun invio da «backup notturno»",
              content_size: 200,
              content_normalized: false,
              storage_backend: "inline",
              severity: "critical",
              severity_source: "missing",
              status: "unread",
              received_at: "2026-08-05T03:31:00Z",
            },
            {
              id: "nr1",
              receiver_id: "r1",
              content_preview: "[notifyhub] «backup notturno» ha ripreso a inviare",
              content_size: 180,
              content_normalized: false,
              storage_backend: "inline",
              severity: "info",
              severity_source: "recovered",
              status: "unread",
              received_at: "2026-08-05T09:00:00Z",
            },
          ],
          next_cursor: null,
          unread_count: 2,
        }),
      ),
    );

    renderWithProviders(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/nessun invio da/)).toBeInTheDocument();
    });
    // Le due notifiche scritte dal server si riconoscono dall'origine, senza
    // dover leggere il contenuto. Si guarda dentro la tabella: le stesse
    // etichette compaiono anche fra le opzioni del filtro.
    const tabella = within(screen.getByRole("table"));
    expect(tabella.getByText("notifica mancante")).toBeInTheDocument();
    expect(tabella.getByText("ripresa degli invii")).toBeInTheDocument();
  });

  it("distingue un ping di avvio da un esito", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "ns1",
              receiver_id: "r1",
              content_preview: "[notifyhub] job=backup avvio host=srv01",
              content_size: 60,
              content_normalized: false,
              storage_backend: "inline",
              severity: "debug",
              severity_source: "explicit",
              phase: "start",
              duration_ms: null,
              exit_code: null,
              status: "unread",
              received_at: "2026-08-05T03:00:01Z",
            },
            {
              id: "ne1",
              receiver_id: "r1",
              content_preview: "[notifyhub] job=backup esito=ok exit=0",
              content_size: 80,
              content_normalized: false,
              storage_backend: "inline",
              severity: "info",
              severity_source: "receiver_default",
              phase: "end",
              duration_ms: 750_123,
              exit_code: 0,
              status: "unread",
              received_at: "2026-08-05T03:12:00Z",
            },
          ],
          next_cursor: null,
          unread_count: 2,
        }),
      ),
    );

    renderWithProviders(<NotificationsPage />);

    await waitFor(() => {
      expect(screen.getByText(/job=backup avvio/)).toBeInTheDocument();
    });
    const tabella = within(screen.getByRole("table"));
    // Solo l'avvio porta la marca: la conclusione e' il caso normale e non ha
    // bisogno di essere annunciata.
    expect(tabella.getAllByText("avvio")).toHaveLength(1);
    expect(tabella.queryByText("conclusione")).not.toBeInTheDocument();
  });

  it("il filtro sull'origine arriva nella richiesta e nel bulk-read", async () => {
    let capturedUrl: URL | null = null;
    let bulkBody: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 });
      }),
      http.post("/api/v1/notifications/bulk-read", async ({ request }) => {
        bulkBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ marked_read: 0 });
      }),
    );

    renderWithProviders(<NotificationsPage />);
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Origine della notifica"), "missing");

    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("source")).toBe("missing");
    });

    // "Segna tutte come lette" non deve agire su cio' che il filtro esclude.
    await user.click(screen.getByRole("button", { name: "Segna tutte come lette" }));
    await waitFor(() => expect(bulkBody).not.toBeNull());
    expect(bulkBody).toMatchObject({ source: "missing" });
  });
});
