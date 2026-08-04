import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReceiverDetailPage from "../ReceiverDetailPage";
import { setRefreshToken } from "../../api/client";
import {
  fixtureReceiver,
  fixtureTestSeverityRule,
  fixtureWrapperScript,
} from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

function renderReceiverDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/receivers/:id" element={<ReceiverDetailPage />} />
    </Routes>,
    ["/receivers/r1"],
  );
}

describe("ReceiverDetailPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("T-UI13 test_prova_severity_mostra_regola: la risposta di prova mostra la regola vincente", async () => {
    const user = userEvent.setup();
    renderReceiverDetail();

    await waitFor(() => {
      expect(screen.getByText(/Contenuto di prova/)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/contenuto di prova/i), "Backup FALLITO");
    await user.click(screen.getByRole("button", { name: "Esegui prova" }));

    await waitFor(() => {
      expect(screen.getByText(/Severity risolta/).closest("p")?.textContent).toContain(
        fixtureTestSeverityRule.matched_pattern,
      );
    });
  });

  it("mostra la soglia di durata configurata e la salva in secondi", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureReceiver, ...inviato });
      }),
    );

    setRefreshToken("refresh-token-fixture"); // fixtureMe di default ha ruolo owner
    renderReceiverDetail();

    // La vista di sola lettura riassume la politica con la durata leggibile.
    await waitFor(() => {
      expect(screen.getByText(/Soglia di durata:/).textContent).toContain("oltre 10m00s → error");
    });

    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    // 600 secondi si presentano come 10 minuti, non come 600 secondi.
    const soglia = screen.getByLabelText("Soglia di durata");
    expect(soglia).toHaveValue(10);
    expect(screen.getByLabelText("Unita della soglia di durata")).toHaveValue("m");

    await user.clear(soglia);
    await user.type(soglia, "15");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).toMatchObject({ duration_threshold_seconds: 900, duration_severity: "error" });
  });

  it("rifiuta la coppia soglia/severity mezza configurata senza chiamare l'API", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.patch("/api/v1/receivers/r1", () => {
        chiamate += 1;
        return HttpResponse.json(fixtureReceiver);
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(
      screen.getByLabelText("Severity oltre la soglia di durata"),
      "nessun effetto",
    );
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Soglia rimasta, severity azzerata: manca la severity, non la soglia.
    expect(await screen.findByRole("alert")).toHaveTextContent(/Scegli la severity/);
    expect(chiamate).toBe(0);

    // Caso opposto: severity scelta e soglia svuotata.
    await user.selectOptions(screen.getByLabelText("Severity oltre la soglia di durata"), "error");
    await user.clear(screen.getByLabelText("Soglia di durata"));
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Imposta una soglia di durata/);
    expect(chiamate).toBe(0);
  });

  it("mostra l'URL di invio deciso dal backend, non l'origine del browser", async () => {
    renderReceiverDetail();

    await waitFor(() => {
      expect(screen.getByText(/URL di invio:/).textContent).toContain(fixtureReceiver.ingest_url);
    });
    // Il comando curl di esempio usa la stessa URL: dietro reverse proxy
    // window.location.origin sarebbe quello giusto solo per caso.
    expect(screen.getByText(new RegExp(`curl --data .* ${fixtureReceiver.ingest_url}`)))
      .toBeInTheDocument();
    expect(screen.getByText(/Slug:/).textContent).toContain("maritime-backup-notturno-");
  });

  it("scarica lo script wrapper col nome scelto dal server", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn((_blob: Blob) => "blob:notifyhub");
    const revokeObjectURL = vi.fn();
    // jsdom non implementa le due: senza stub il download esploderebbe qui e non
    // in produzione, dove esistono entrambe.
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    // Un click vero su <a download> in jsdom prova a navigare: si intercetta il
    // click e si ispeziona l'ancora costruita dalla pagina.
    const clicked: { download: string; href: string }[] = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push({ download: this.download, href: this.href });
      });

    try {
      renderReceiverDetail();
      await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: "Scarica lo script" }));

      await waitFor(() => expect(clicked).toHaveLength(1));
      expect(clicked[0].download).toBe("notifyhub-run-backup-notturno.sh");
      expect(clicked[0].href).toBe("blob:notifyhub");
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:notifyhub");

      // Il contenuto passato al Blob e' quello servito dal backend, slug e URL
      // compresi: la pagina non ricompone lo script da sola.
      const blob = createObjectURL.mock.calls[0][0];
      // Il Blob di jsdom non ha .text() e non e' un Blob per Response (altro
      // realm): l'unico lettore disponibile qui e' FileReader.
      const contenuto = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsText(blob);
      });
      expect(contenuto).toBe(fixtureWrapperScript);
      expect(blob.type).toBe("text/x-shellscript");
    } finally {
      clickSpy.mockRestore();
    }
  });

  it("mostra l'errore se il download dello script fallisce", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/receivers/r1/wrapper-script", () =>
        HttpResponse.json(
          {
            type: "/problems/internal-error",
            title: "Internal Server Error",
            detail: "Wrapper script template unavailable: notifyhub-run.sh not found",
          },
          { status: 500 },
        ),
      ),
    );

    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Scarica lo script" }));

    expect(await screen.findByText(/Wrapper script template unavailable/)).toBeInTheDocument();
  });

  it("riassume la sorveglianza dell'attesa e lo stato dell'ultimo invio", async () => {
    renderReceiverDetail();

    await waitFor(() => {
      expect(screen.getByText(/Sorveglianza dell'attesa:/).textContent).toContain(
        "ogni 1g, tolleranza 30m00s → critical",
      );
    });
    // Le tre date che rispondono a "sono in ritardo?" e "e' anche partito?".
    const stato = screen.getByText(/Ultima conclusione:/).textContent ?? "";
    expect(stato).toContain("Allarme se non arriva entro");
    expect(stato).toContain("Ultimo avvio:");
  });

  it("segnala in evidenza un receiver in ritardo", async () => {
    server.use(
      http.get("/api/v1/receivers/r1", () =>
        HttpResponse.json({
          ...fixtureReceiver,
          expected_late: true,
          missing_alerted_at: "2026-08-05T03:31:00Z",
        }),
      ),
    );

    renderReceiverDetail();

    expect(await screen.findByRole("alert")).toHaveTextContent(/In ritardo/);
    expect(screen.getByRole("alert")).toHaveTextContent(/Assenza segnalata il/);
  });

  it("passa dall'intervallo all'espressione cron e la salva col fuso", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureReceiver, ...inviato });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    // 86400 secondi si presentano come 1 giorno, non come 86400 secondi.
    expect(screen.getByLabelText("Mi aspetto un invio ogni")).toHaveValue(1);
    expect(screen.getByLabelText("Unita dell'intervallo atteso")).toHaveValue("g");

    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");
    await user.type(screen.getByLabelText("Espressione cron"), "0 3 * * 1-5");
    await user.selectOptions(
      screen.getByLabelText("Fuso dell'espressione"),
      "Europe/Rome",
    );
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).toMatchObject({
      expected_cron: "0 3 * * 1-5",
      expected_timezone: "Europe/Rome",
      // I due modi sono alternativi: passando al cron l'intervallo va azzerato.
      expected_every_seconds: null,
      expected_grace_seconds: 1800,
      missing_severity: "critical",
    });
  });

  it("il menu dei fusi non si limita a UTC", async () => {
    const user = userEvent.setup();
    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");

    // Con un campo + datalist il browser filtrava i suggerimenti per
    // sottostringa del valore scritto: con "UTC" dentro si vedeva solo UTC.
    const fusi = screen.getByLabelText("Fuso dell'espressione");
    const opzioni = within(fusi).getAllByRole("option");
    expect(opzioni.length).toBeGreaterThan(100);

    const valori = opzioni.map((o) => (o as HTMLOptionElement).value);
    expect(valori).toContain("Europe/Rome");
    expect(valori).toContain("America/New_York");
    expect(valori).toContain("UTC");
    // Raggruppati per area, con i consigliati in cima.
    expect(within(fusi).getByRole("group", { name: "Consigliati" })).toBeInTheDocument();
    expect(within(fusi).getByRole("group", { name: "Europe" })).toBeInTheDocument();
  });

  it("rifiuta un'espressione cron malformata senza chiamare l'API", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.patch("/api/v1/receivers/r1", () => {
        chiamate += 1;
        return HttpResponse.json(fixtureReceiver);
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");
    await user.type(screen.getByLabelText("Espressione cron"), "0 3 *");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/5 campi/);
    expect(chiamate).toBe(0);
  });

  it("spegne la sorveglianza mandando null su tutti i campi", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureReceiver, ...inviato });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(screen.getByLabelText("Attesa"), "off");
    // Spenta: i campi della politica scompaiono dal form.
    expect(screen.queryByLabelText("Tolleranza sul ritardo")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).toMatchObject({
      expected_every_seconds: null,
      expected_cron: null,
      expected_timezone: null,
      expected_grace_seconds: null,
      missing_severity: null,
    });
  });

  it("avverte che --only-on-failure e la sorveglianza non stanno insieme", async () => {
    const user = userEvent.setup();
    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText(/Slug:/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    expect(screen.getByText(/--only-on-failure/)).toBeInTheDocument();
  });

  it("T-UI14 test_rotate_slug_nascosto_al_member: con ruolo member il pulsante non è nel documento", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: "u1",
          email: "member@acme.test",
          role: "member",
          tenant_id: "t1",
          tenant_name: "ACME",
        }),
      ),
    );
    setRefreshToken("refresh-token-fixture");

    renderReceiverDetail();

    await waitFor(() => {
      expect(screen.getByText(/Slug:/)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Rigenera slug" })).not.toBeInTheDocument();
  });
});
