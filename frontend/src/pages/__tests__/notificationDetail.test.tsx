// Dettaglio della notifica: la schermata dove un operatore legge un allarme alle
// tre di notte. Era al 76% di righe ma al **25% di funzioni**: segna-come-letta,
// elimina e scarica-contenuto non erano mai stati eseguiti da un test.

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NotificationDetailPage from "../NotificationDetailPage";
import { setRefreshToken } from "../../api/client";
import {
  fixtureNotificationDetailInline,
  fixtureNotificationDetailObject,
} from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

function renderDetail(id: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/notifications/:id" element={<NotificationDetailPage />} />
      <Route path="/notifications" element={<p>elenco notifiche</p>} />
    </Routes>,
    [`/notifications/${id}`],
  );
}

function serviDettaglio(dettaglio: Record<string, unknown>) {
  server.use(http.get("/api/v1/notifications/n1", () => HttpResponse.json(dettaglio)));
}

/** Testo di una coppia etichetta/valore della scheda: i fatti stanno in una
 *  griglia di etichette e valori, non piu' in frasi "Etichetta: valore". */
function campo(etichetta: string): string {
  return screen.getByText(etichetta).parentElement?.textContent ?? "";
}

describe("NotificationDetailPage", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture"); // fixtureMe di default: owner
  });

  it("T-UI10 test_payload_offloaded_mostra_download: storage_backend object mostra il download, non il corpo", async () => {
    renderDetail("n4");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Scarica contenuto completo" })).toBeInTheDocument();
    });

    expect(screen.queryByText(fixtureNotificationDetailObject.content_preview)).not.toBeInTheDocument();
    expect(document.querySelector("pre")).not.toBeInTheDocument();
  });

  it("T-UI11 test_origine_severity_mostrata: con severity_source rule compare il pattern vincente", async () => {
    renderDetail("n1");

    await waitFor(() => {
      expect(screen.getByText(fixtureNotificationDetailInline.matched_pattern)).toBeInTheDocument();
    });
  });

  it("mostra i fatti dell'esecuzione: origine, durata, exit code, fase, sorgente", async () => {
    serviDettaglio({ ...fixtureNotificationDetailInline, phase: "end" });
    renderDetail("n1");

    await waitFor(() => {
      expect(campo("Origine della severity")).toContain("regola del receiver");
    });
    expect(campo("Durata esecuzione")).toContain("12m30s");
    expect(campo("Exit code")).toContain("1");
    expect(campo("Fase dell'esecuzione")).toContain("conclusione");
    expect(campo("Sorgente")).toContain("203.0.113.5");
    expect(screen.getByText(fixtureNotificationDetailInline.content)).toBeInTheDocument();
  });

  it("una notifica di assenza dice che l'ha scritta il server", async () => {
    serviDettaglio({
      ...fixtureNotificationDetailInline,
      severity: "critical",
      severity_source: "missing",
      matched_pattern: null,
      duration_ms: null,
      exit_code: null,
      phase: null,
      source_ip: null,
      content: "[notifyhub] nessun invio da «backup notturno»",
    });
    renderDetail("n1");

    await waitFor(() => {
      expect(campo("Origine della severity")).toContain("notifica mancante");
    });
    expect(screen.getByText(/generata da NotifyHub, non inviata da nessuno/)).toBeInTheDocument();
    // Senza mittente non si mostra una sorgente inventata.
    expect(screen.queryByText("Sorgente")).not.toBeInTheDocument();
    expect(screen.queryByText(/Exit code/)).not.toBeInTheDocument();
  });

  it("un ping di avvio si distingue da un esito", async () => {
    serviDettaglio({
      ...fixtureNotificationDetailInline,
      severity: "debug",
      severity_source: "explicit",
      phase: "start",
      duration_ms: null,
      exit_code: null,
    });
    renderDetail("n1");

    await waitFor(() => {
      expect(campo("Fase dell'esecuzione")).toContain("avvio");
    });
    expect(screen.getByText(/dice che il job è partito/)).toBeInTheDocument();
  });

  it("T-DET3 segna come letta commuta in segna come non letta", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    let stato = "unread";
    server.use(
      http.get("/api/v1/notifications/n1", () =>
        HttpResponse.json({ ...fixtureNotificationDetailInline, status: stato }),
      ),
      http.patch("/api/v1/notifications/n1", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        stato = "read";
        return HttpResponse.json({ ...fixtureNotificationDetailInline, status: "read" });
      }),
    );
    renderDetail("n1");

    await user.click(await screen.findByRole("button", { name: "Segna come letta" }));

    await waitFor(() => expect(inviato).toEqual({ status: "read" }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Segna come letta" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Segna come non letta" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Segna come non letta" }));
    await waitFor(() => expect(inviato).toEqual({ status: "unread" }));
  });

  it("T-DET1 il dettaglio mostra entrambi i toggle e la pill di verifica", async () => {
    renderDetail("n1");

    await waitFor(() => {
      expect(screen.getByText("Origine della severity")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Segna come letta" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Segna come non verificata" })).toBeInTheDocument();
    expect(screen.getByText("Verificata")).toBeInTheDocument();
  });

  it("T-DET2 toggle verifica manda verified true", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    let verificata = false;
    server.use(
      http.get("/api/v1/notifications/n1", () =>
        HttpResponse.json({ ...fixtureNotificationDetailInline, verified: verificata }),
      ),
      http.patch("/api/v1/notifications/n1", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        if (inviato.verified === true) verificata = true;
        return HttpResponse.json({ ...fixtureNotificationDetailInline, verified: true });
      }),
    );
    renderDetail("n1");

    await user.click(await screen.findByRole("button", { name: "Segna come verificata" }));

    await waitFor(() => expect(inviato).toEqual({ verified: true }));
    await waitFor(() => {
      expect(screen.getByText("Verificata")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Segna come non verificata" })).toBeInTheDocument();
  });

  it("il contenuto su object storage si scarica col Bearer, non con un link diretto", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn((_blob: Blob) => "blob:contenuto");
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const clicked: string[] = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(this.download);
      });
    let contenutoChiesto = false;

    server.use(
      http.get("/api/v1/notifications/n1", () =>
        HttpResponse.json({ ...fixtureNotificationDetailObject, id: "n1" }),
      ),
      http.get("/api/v1/notifications/n1/content", () => {
        contenutoChiesto = true;
        return HttpResponse.text("corpo completo dal deposito");
      }),
    );

    try {
      renderDetail("n1");
      expect(
        // Le dimensioni si leggono, non si contano: 2097152 byte = 2 MB.
        await screen.findByText(/Contenuto salvato su object storage \(2 MB\)/),
      ).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Scarica contenuto completo" }));

      await waitFor(() => expect(clicked).toEqual(["notifica-n1.txt"]));
      // Un <a href download> partirebbe senza header Authorization e prenderebbe
      // 401: il contenuto passa dal client API (che aggiunge il Bearer e sa
      // rinfrescarlo) e finisce in un blob.
      expect(contenutoChiesto).toBe(true);
      const blob = createObjectURL.mock.calls[0][0];
      const testo = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.readAsText(blob);
      });
      expect(testo).toBe("corpo completo dal deposito");
    } finally {
      clickSpy.mockRestore();
    }
  });

  it("elimina e torna all'elenco", async () => {
    const user = userEvent.setup();
    let eliminata = false;
    server.use(
      http.get("/api/v1/notifications/n1", () =>
        HttpResponse.json(fixtureNotificationDetailInline),
      ),
      http.delete("/api/v1/notifications/n1", () => {
        eliminata = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderDetail("n1");

    await user.click(await screen.findByRole("button", { name: "Elimina" }));
    // L'eliminazione passa da una conferma: un clic solo non deve cancellare
    // una notifica che si stava leggendo.
    const dialogo = within(await screen.findByRole("dialog"));
    expect(eliminata).toBe(false);
    await user.click(dialogo.getByRole("button", { name: "Elimina" }));

    await waitFor(() => expect(eliminata).toBe(true));
    // Restare sulla pagina di una notifica cancellata mostrerebbe un 404.
    expect(await screen.findByText("elenco notifiche")).toBeInTheDocument();
  });

  it("il viewer legge ma non elimina", async () => {
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
      http.get("/api/v1/notifications/n1", () =>
        HttpResponse.json(fixtureNotificationDetailInline),
      ),
    );
    renderDetail("n1");

    await waitFor(() => {
      expect(screen.getByText("Origine della severity")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Elimina" })).not.toBeInTheDocument();
    // Segnare come letta resta permesso: non tocca il contenuto.
    expect(screen.getByRole("button", { name: "Segna come letta" })).toBeInTheDocument();
    // Anche il toggle di verifica non e' un'azione distruttiva: il viewer lo vede.
    expect(screen.getByRole("button", { name: "Segna come non verificata" })).toBeInTheDocument();
  });

  it("una notifica che non esiste mostra l'errore, non una pagina vuota", async () => {
    server.use(
      http.get("/api/v1/notifications/n1", () =>
        HttpResponse.json(
          {
            type: "/problems/not-found",
            title: "Not Found",
            status: 404,
            detail: "Notification not found.",
          },
          { status: 404 },
        ),
      ),
    );
    renderDetail("n1");

    expect(await screen.findByText(/Notification not found/)).toBeInTheDocument();
  });
});
