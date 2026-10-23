import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import ReceiverNotificationsTable from "../ReceiverNotificationsTable";
import { setRefreshToken } from "../../api/client";
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

const viewerMe = {
  id: "u9",
  email: "viewer@acme.test",
  role: "viewer",
  tenant_id: "t1",
  tenant_name: "ACME",
};

describe("ReceiverNotificationsTable", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture"); // fixtureMe di default ha ruolo owner
  });

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
    const link = tabella.getAllByRole("link", { name: /^Apri/ });
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
    const cella = screen.getByRole("link", { name: /^Apri/ }).closest(".content-cell") as HTMLElement;
    expect(cella).not.toBeNull();
    expect(within(cella).getByText("Contenuto normalizzato")).toBeInTheDocument();
    expect(within(cella).getByText("2 MB su object storage")).toBeInTheDocument();
    expect(within(cella).getByTitle("2097152 byte")).toBeInTheDocument();
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
      await screen.findByRole("button", { name: "Segna tutte come lette: Backup notturno" }),
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
    expect(screen.getByText("Disabilitato")).toBeInTheDocument();
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
    await user.click((await tabella.findAllByRole("button", { name: /^Segna come letta/ }))[0]);

    // Il messaggio compare due volte, e deve: il toast lo dice subito, il
    // banner dentro la tabella resta e dice quale tabella ha fallito.
    const occorrenze = await screen.findAllByText(/Serve il ruolo member/);
    expect(occorrenze.length).toBeGreaterThanOrEqual(2);
    const sezione = within(screen.getByRole("region", { name: /Notifiche di/ }));
    expect(sezione.getByRole("alert")).toHaveTextContent(/Serve il ruolo member/);
  });

  it("T-RCV6 un receiver senza notifiche mostra la tabella vuota, non sparisce", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json({ notifications: [], next_cursor: null, unread_count: 0 }),
      ),
    );

    renderTable();

    expect(await screen.findByText("Nessuna notifica trovata.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Backup notturno" })).toBeInTheDocument();
  });

  it("T-RCV9 'segna tutte come lette' manda anche lo stato e il testo filtrati", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/notifications/bulk-read", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ marked_read: 1 });
      }),
    );

    renderTable({ group_id: "g1", status: "unread", q: "backup" } as never);
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: "Segna tutte come lette: Backup notturno" }),
    );

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      group_id: "g1",
      receiver_id: "r1",
      status: "unread",
      q: "backup",
    });
  });

  it("T-RCV10 con il filtro 'solo lette' non propone di segnarle tutte come lette", async () => {
    renderTable({ group_id: "g1", status: "read" } as never);

    const tabella = within(await screen.findByRole("table"));
    // La sessione e' caricata (le azioni di riga ci sono), il pulsante no.
    expect(
      (await tabella.findAllByRole("button", { name: /^Segna come non letta/ })).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: /Segna tutte come lette/ }),
    ).not.toBeInTheDocument();
  });

  it("T-RCV11 il viewer vede le notifiche ma non le azioni ne' il link al receiver", async () => {
    server.use(http.get("/api/v1/auth/me", () => HttpResponse.json(viewerMe)));
    let meCaricato = false;
    server.events.on("response:mocked", ({ request }) => {
      if (new URL(request.url).pathname === "/api/v1/auth/me") meCaricato = true;
    });

    try {
      renderTable();

      await screen.findByRole("table");
      await waitFor(() => expect(meCaricato).toBe(true));
      // Il profilo e' arrivato: si lascia a React il giro per applicarlo, cosi'
      // le assenze qui sotto non passano solo perche' la sessione carica ancora.
      await new Promise((resolve) => setTimeout(resolve, 50));

      // Il backend risponderebbe 403 (require_member) e /receivers/:id e'
      // chiusa al viewer da RequireRole: niente pulsanti, nome come testo.
      expect(screen.getByRole("heading", { name: "Backup notturno" })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Backup notturno" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Segna come/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Segna tutte/ })).not.toBeInTheDocument();
    } finally {
      server.events.removeAllListeners();
    }
  });

  it("T-RCV12 ogni riga ha pulsanti e link con un nome suo, non ripetuto fra le righe", async () => {
    renderTable();

    const tabella = within(await screen.findByRole("table"));
    const pulsanti = tabella.getAllByRole("button", { name: /^Segna come (letta|non letta)/ });
    const nomi = pulsanti.map((b) => b.getAttribute("aria-label") ?? "");
    // Due righe con lo stesso nome non si distinguono per chi usa lo screen reader.
    expect(nomi.length).toBeGreaterThanOrEqual(2);
    expect(new Set(nomi).size).toBe(nomi.length);

    const apri = tabella.getAllByRole("link", { name: /^Apri la notifica di/ });
    expect(new Set(apri.map((a) => a.getAttribute("aria-label"))).size).toBe(apri.length);
  });

  it("T-RCV13 l'ultima colonna, quella delle azioni, ha un nome anche se non ha titolo", async () => {
    renderTable();

    const tabella = within(await screen.findByRole("table"));
    const intestazioni = tabella.getAllByRole("columnheader");
    expect(intestazioni[intestazioni.length - 1]).toHaveAccessibleName("Azioni");
  });

  it("T-RCV14 se il caricamento fallisce la tabella non dice «Nessuna notifica»", async () => {
    server.use(
      http.get("/api/v1/notifications", () =>
        HttpResponse.json(
          { type: "/problems/internal", title: "Internal Server Error", status: 500 },
          { status: 500 },
        ),
      ),
    );

    renderTable();

    expect(
      await screen.findByText("Elenco non disponibile per un errore di caricamento."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Nessuna notifica trovata.")).not.toBeInTheDocument();
  });
});
