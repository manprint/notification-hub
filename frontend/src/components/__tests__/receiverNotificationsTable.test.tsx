import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import ReceiverNotificationsTable from "../ReceiverNotificationsTable";
import {
  fixtureNotificationsPage1,
  fixtureReceiver,
} from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import type { ReceiverOut } from "../../api/types";
import { renderWithProviders } from "../../pages/__tests__/testUtils";

const receiver = fixtureReceiver as unknown as ReceiverOut;

function renderTable(filters = { group_id: "g1" }) {
  return renderWithProviders(
    <ReceiverNotificationsTable receiver={receiver} filters={filters} />,
    ["/notifications?group_id=g1"],
  );
}

describe("ReceiverNotificationsTable", () => {
  it("T-RCV1 chiede solo le notifiche del proprio receiver", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get("/api/v1/notifications", ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json(fixtureNotificationsPage1);
      }),
    );

    renderTable({ group_id: "g1", severity_min: "error" } as never);

    await waitFor(() => {
      expect(capturedUrl?.searchParams.get("receiver_id")).toBe("r1");
      expect(capturedUrl?.searchParams.get("group_id")).toBe("g1");
      expect(capturedUrl?.searchParams.get("severity_min")).toBe("error");
    });
  });

  it("T-RCV2 la colonna Contenuto mostra 'Apri' e non il messaggio", async () => {
    renderTable();

    const tabella = within(await screen.findByRole("table"));
    const link = tabella.getAllByRole("link", { name: "Apri" });
    expect(link).toHaveLength(2);
    expect(link[0]).toHaveAttribute("href", "/notifications/n1");

    // Il testo del messaggio non deve comparire in lista: si legge aprendolo.
    expect(screen.queryByText(/Backup FALLITO/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tutto ok/)).not.toBeInTheDocument();
  });

  it("T-RCV3 le pill sul payload restano accanto ad 'Apri'", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "nobj",
              receiver_id: "r1",
              content_preview: "corpo lunghissimo",
              content_size: 2_097_152,
              content_normalized: true,
              storage_backend: "object",
              severity: "critical",
              severity_source: "explicit",
              phase: null,
              status: "unread",
              verified: false,
              received_at: "2026-08-01T05:00:00Z",
            },
          ],
          next_cursor: null,
          unread_count: 1,
        }),
      ),
    );

    renderTable();

    await screen.findByRole("table");
    const cella = screen.getByRole("link", { name: "Apri" }).closest(".content-cell") as HTMLElement;
    expect(cella).not.toBeNull();
    expect(within(cella).getByText("contenuto normalizzato")).toBeInTheDocument();
    expect(within(cella).getByText("2097152 byte su object storage")).toBeInTheDocument();
  });

  it("T-RCV4 l'intestazione porta il nome del receiver e linka al suo dettaglio", async () => {
    renderTable();

    const link = await screen.findByRole("link", { name: "Backup notturno" });
    expect(link).toHaveAttribute("href", "/receivers/r1");
  });

  it("T-RCV5 'segna tutte come lette' della tabella agisce sul solo receiver, coi filtri correnti", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/notifications/bulk-read", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ marked_read: 2 });
      }),
    );

    renderTable({ group_id: "g1", verified: false } as never);
    const user = userEvent.setup();

    await screen.findByRole("table");
    await user.click(
      screen.getByRole("button", { name: "Segna tutte come lette: Backup notturno" }),
    );

    await waitFor(() => {
      expect(body).not.toBeNull();
    });
    expect(body).toMatchObject({ group_id: "g1", receiver_id: "r1", verified: false });
  });

  it("T-RCV7 un receiver disabilitato lo dichiara nell'intestazione", async () => {
    renderWithProviders(
      <ReceiverNotificationsTable
        receiver={{ ...receiver, status: "disabled" }}
        filters={{ group_id: "g1" }}
      />,
      ["/notifications?group_id=g1"],
    );

    await screen.findByRole("table");
    expect(screen.getByText("disabilitato")).toBeInTheDocument();
  });

  it("T-RCV8 un errore sull'azione resta dentro la sua tabella", async () => {
    server.use(
      http.patch("/api/v1/notifications/:id", () =>
        HttpResponse.json(
          {
            type: "/problems/forbidden",
            title: "Forbidden",
            status: 403,
            detail: "Serve il ruolo member per marcare una notifica.",
          },
          { status: 403 },
        ),
      ),
    );

    renderTable();
    const user = userEvent.setup();

    const tabella = within(await screen.findByRole("table"));
    await user.click(tabella.getAllByRole("button", { name: "Segna come letta" })[0]);

    expect(await screen.findByText(/Serve il ruolo member/)).toBeInTheDocument();
  });

  it("T-RCV6 un receiver senza notifiche mostra la tabella vuota, non sparisce", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 }),
      ),
    );

    renderTable();

    expect(await screen.findByText("Nessuna notifica trovata.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Backup notturno" })).toBeInTheDocument();
  });
});
