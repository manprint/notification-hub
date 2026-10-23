import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReceiverDetailPage from "../ReceiverDetailPage";
import { setRefreshToken } from "../../api/client";
import {
  fixtureReceiver,
  fixtureSeverityReplay,
  fixtureTestSeverityRule,
  fixtureWrapperScript,
} from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { REVOKE_DELAY_MS } from "../../lib/download";
import { renderWithProviders } from "./testUtils";

/** Testo completo di una cella della griglia dei dettagli: l'etichetta e il
 *  valore stanno in due elementi fratelli. */
function campo(etichetta: string): string {
  return screen.getByText(etichetta).parentElement?.textContent ?? "";
}

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
      expect(campo("Soglia di durata")).toContain("oltre 10m00s → Errore");
    });

    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    // 600 secondi si presentano come 10 minuti, non come 600 secondi.
    const soglia = screen.getByLabelText("Soglia di durata");
    expect(soglia).toHaveValue(10);
    expect(screen.getByLabelText("Unità della soglia di durata")).toHaveValue("m");

    await user.clear(soglia);
    await user.type(soglia, "15");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    // Solo la soglia è cambiata: la severity salvata non viaggia nella PATCH.
    expect(inviato).toEqual({ duration_threshold_seconds: 900 });
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
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
      expect(campo("URL di invio")).toContain(fixtureReceiver.ingest_url);
    });
    // Il comando curl di esempio usa la stessa URL: dietro reverse proxy
    // window.location.origin sarebbe quello giusto solo per caso.
    expect(screen.getByText(new RegExp(`curl --data .* ${fixtureReceiver.ingest_url}`)))
      .toBeInTheDocument();
    expect(campo("Slug")).toContain("maritime-backup-notturno-");
  });

  it("scarica lo script wrapper col nome scelto dal server", async () => {
    // Timer finti: l'URL del blob si revoca dopo REVOKE_DELAY_MS, non subito.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const createObjectURL = vi.fn((_blob: Blob) => "blob:notifyhub");
    const revokeObjectURL = vi.fn();
    // jsdom non implementa le due: senza stub il download esploderebbe qui e non
    // in produzione, dove esistono entrambe.
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    // Un click vero su <a download> in jsdom prova a navigare: si intercetta il
    // click e si ispeziona l'ancora costruita dalla pagina.
    const clicked: { download: string; href: string; inDom: boolean }[] = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push({
          download: this.download,
          href: this.href,
          inDom: document.body.contains(this),
        });
      });

    try {
      renderReceiverDetail();
      await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: "Scarica lo script" }));

      await waitFor(() => expect(clicked).toHaveLength(1));
      expect(clicked[0].download).toBe("notifyhub-run-backup-notturno.sh");
      expect(clicked[0].href).toBe("blob:notifyhub");
      // Firefox ignora il click su un'ancora fuori dal documento, e Firefox e
      // Safari scaricano in modo asincrono: revocare l'URL subito dopo il click
      // faceva fallire lo scaricamento.
      expect(clicked[0].inDom).toBe(true);
      expect(revokeObjectURL).not.toHaveBeenCalled();
      vi.advanceTimersByTime(REVOKE_DELAY_MS);
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
      vi.useRealTimers();
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Scarica lo script" }));

    // Due volte: l'avviso immediato in basso e il banner che resta accanto al
    // pulsante col dettaglio del problema.
    expect((await screen.findAllByText(/Wrapper script template unavailable/)).length)
      .toBeGreaterThanOrEqual(2);
  });

  it("riassume la sorveglianza dell'attesa e lo stato dell'ultimo invio", async () => {
    renderReceiverDetail();

    await waitFor(() => {
      expect(campo("Politica in vigore")).toContain("ogni 1g, tolleranza 30m00s → Critica");
    });
    // Le tre date che rispondono a "sono in ritardo?" e "e' anche partito?".
    expect(campo("Ultima conclusione")).not.toMatch(/mai$/);
    expect(campo("Ultimo avvio")).not.toMatch(/mai$/);
    expect(campo("Allarme se non arriva entro")).not.toBe("");
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    // 86400 secondi si presentano come 1 giorno, non come 86400 secondi.
    expect(screen.getByLabelText("Mi aspetto un invio ogni")).toHaveValue(1);
    expect(screen.getByLabelText("Unità dell'intervallo atteso")).toHaveValue("g");

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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");
    await user.type(screen.getByLabelText("Espressione cron"), "0 3 *");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(await screen.findAllByRole("alert")).not.toHaveLength(0);
    expect(
      screen.getAllByRole("alert").some((n) => /5 campi/.test(n.textContent ?? "")),
    ).toBe(true);
    expect(chiamate).toBe(0);
  });

  it("T-VAL1 impedisce di salvare un cron con un campo fuori range", async () => {
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");
    await user.type(screen.getByLabelText("Espressione cron"), "99 3 * * *");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(
      (await screen.findAllByRole("alert")).some((n) =>
        /non valida/.test(n.textContent ?? ""),
      ),
    ).toBe(true);
    expect(chiamate).toBe(0);
  });

  it("T-VAL2 mostra subito l'errore del cron, prima di ogni salvataggio", async () => {
    const user = userEvent.setup();
    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");
    await user.type(screen.getByLabelText("Espressione cron"), "0 3 *");

    expect(
      screen.getAllByRole("alert").some((n) => /5 campi/.test(n.textContent ?? "")),
    ).toBe(true);
  });

  it("T-VAL3 rifiuta un fuso orario non valido senza chiamare l'API", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    // Il fuso errato arriva gia' salvato nel receiver: torno in modalita' cron
    // con quel valore e provo a salvare di nuovo.
    server.use(
      http.get("/api/v1/receivers/r1", () =>
        HttpResponse.json({
          ...fixtureReceiver,
          expected_every_seconds: null,
          expected_cron: "0 3 * * *",
          expected_timezone: "Europa/Roma",
        }),
      ),
      http.patch("/api/v1/receivers/r1", () => {
        chiamate += 1;
        return HttpResponse.json(fixtureReceiver);
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(
      (await screen.findAllByRole("alert")).some((n) =>
        /non valido/.test(n.textContent ?? ""),
      ),
    ).toBe(true);
    expect(chiamate).toBe(0);
  });

  it("T-PRE1 mostra le prossime tre esecuzioni del cron", async () => {
    const user = userEvent.setup();
    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");
    await user.type(screen.getByLabelText("Espressione cron"), "0 3 * * 1-5");

    const lista = screen.getByLabelText("Prossime esecuzioni");
    const voci = within(lista).getAllByRole("listitem");
    expect(voci).toHaveLength(3);
    const testi = voci.map((v) => v.textContent ?? "");
    expect(new Set(testi).size).toBe(3);
    for (const testo of testi) {
      expect(testo.trim()).not.toBe("");
    }
  });

  it("T-PRE2 mantiene la preview corretta quando cambia il fuso", async () => {
    const user = userEvent.setup();
    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.selectOptions(screen.getByLabelText("Attesa"), "cron");
    await user.type(screen.getByLabelText("Espressione cron"), "0 3 * * 1-5");
    await user.selectOptions(
      screen.getByLabelText("Fuso dell'espressione"),
      "Europe/Rome",
    );

    // La preview ricalcola e resta una lista di tre voci, con l'ora del cron
    // (03:00) espressa nel fuso selezionato. La sensibilita' al fuso dell'ora
    // mostrata e' provata dai test della libreria (cron.test.ts).
    const lista = screen.getByLabelText("Prossime esecuzioni");
    const voci = within(lista).getAllByRole("listitem");
    expect(voci).toHaveLength(3);
    expect(new Set(voci.map((v) => v.textContent ?? "")).size).toBe(3);
    for (const voce of voci) {
      expect(voce.textContent).toContain("03:00");
    }
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    expect(screen.getByText(/--only-on-failure/)).toBeInTheDocument();
  });

  it("chiede conferma prima di rigenerare lo slug", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.post("/api/v1/receivers/r1/rotate-slug", () => {
        chiamate += 1;
        return HttpResponse.json({ ...fixtureReceiver, slug: "maritime-backup-notturno-nuovo" });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Rigenera slug" }));
    // La conferma dice cosa si rompe: i job che usano il vecchio slug.
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent(/smette di funzionare/);
    expect(chiamate).toBe(0);

    // Annullando non parte niente: e' l'azione che invalida gli script gia'
    // distribuiti, non deve bastare un click di troppo.
    await user.click(within(dialog).getByRole("button", { name: "Annulla" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(chiamate).toBe(0);

    await user.click(screen.getByRole("button", { name: "Rigenera slug" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Rigenera slug" }),
    );

    await waitFor(() => expect(chiamate).toBe(1));
    // Riscontro esplicito: lo slug e' cambiato e i job vanno aggiornati.
    expect(await screen.findByText(/Slug rigenerato/)).toBeInTheDocument();
  });

  it("disabilita e riattiva il receiver dalla sua pagina", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    let stato = "active";
    server.use(
      http.get("/api/v1/receivers/r1", () =>
        HttpResponse.json({ ...fixtureReceiver, status: stato }),
      ),
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        stato = String(inviato.status);
        return HttpResponse.json({ ...fixtureReceiver, status: stato });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Disabilita receiver" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Disabilita receiver" }),
    );

    await waitFor(() => expect(inviato).toMatchObject({ status: "disabled" }));
    // Lo stato si legge nella pagina, non solo nel toast che sparisce.
    expect(await screen.findByRole("button", { name: "Riattiva receiver" })).toBeInTheDocument();
    await waitFor(() => expect(campo("Stato del receiver")).toContain("Disabilitato"));

    await user.click(screen.getByRole("button", { name: "Riattiva receiver" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Riattiva receiver" }),
    );
    await waitFor(() => expect(inviato).toMatchObject({ status: "active" }));
  });

  it("conferma il salvataggio delle impostazioni con un riscontro a schermo", async () => {
    const user = userEvent.setup();
    server.use(
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureReceiver, ...body });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    const nome = screen.getByLabelText("Nome");
    await user.clear(nome);
    await user.type(nome, "Backup notturno bis");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Il modulo si chiude e l'esito e' scritto, non dedotto dal fatto che il
    // modulo si sia chiuso.
    expect(await screen.findByText(/Impostazioni del receiver salvate/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Modifica receiver" })).toBeInTheDocument(),
    );
  });

  it("rifiuta il salvataggio con il nome vuoto senza chiamare l'API", async () => {
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    // Solo spazi: `required` del browser lo lascia passare, il controllo del
    // modulo no.
    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "   ");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(await screen.findByText(/Il nome del receiver è obbligatorio/)).toBeInTheDocument();
    expect(chiamate).toBe(0);
    // L'errore e' legato al campo, non solo scritto in fondo al modulo.
    expect(screen.getByLabelText("Nome")).toHaveAttribute("aria-invalid", "true");
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
      expect(screen.getByText("Slug")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Rigenera slug" })).not.toBeInTheDocument();
  });
  it("T-NAV1 passando a un altro receiver lo stato della pagina riparte da zero", async () => {
    const user = userEvent.setup();
    const receiverB = { ...fixtureReceiver, id: "r2", name: "Pulizia log", rate_limit_per_min: 5 };
    let patchSuB: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/receivers/r2", () => HttpResponse.json(receiverB)),
      http.get("/api/v1/receivers/r2/severity-rules", () => HttpResponse.json([])),
      http.patch("/api/v1/receivers/r2", async ({ request }) => {
        patchSuB = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...receiverB, ...patchSuB });
      }),
    );
    function VaiAB() {
      const navigate = useNavigate();
      return <button onClick={() => navigate("/receivers/r2")}>Vai a B</button>;
    }

    setRefreshToken("refresh-token-fixture");
    renderWithProviders(
      <>
        <VaiAB />
        <Routes>
          <Route path="/receivers/:id" element={<ReceiverDetailPage />} />
        </Routes>
      </>,
      ["/receivers/r1"],
    );
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

    // Stato di A: una prova di severity eseguita e il modulo aperto e toccato.
    await user.type(screen.getByLabelText(/contenuto di prova/i), "Backup FALLITO");
    await user.click(screen.getByRole("button", { name: "Esegui prova" }));
    expect(await screen.findByText(/Severity risolta/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "Nome scritto su A");

    await user.click(screen.getByRole("button", { name: "Vai a B" }));

    expect(await screen.findByRole("heading", { name: "Pulizia log" })).toBeInTheDocument();
    // Niente di A resta addosso a B: modulo chiuso, prova azzerata.
    expect(screen.getByRole("button", { name: "Modifica receiver" })).toBeInTheDocument();
    expect(screen.queryByText(/Severity risolta/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    expect(screen.getByLabelText("Nome")).toHaveValue("Pulizia log");
    expect(screen.getByLabelText("Rate limit (al minuto)")).toHaveValue(5);
    await user.clear(screen.getByLabelText("Rate limit (al minuto)"));
    await user.type(screen.getByLabelText("Rate limit (al minuto)"), "7");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(patchSuB).not.toBeNull());
    // Il nome scritto su A non arriva a B, e nemmeno il nome di B: non è cambiato.
    expect(patchSuB).toEqual({ rate_limit_per_min: 7 });
  });

  it("T-TZ1 un cron salvato senza fuso resta in UTC e una rinomina non lo riscrive", async () => {
    const user = userEvent.setup();
    const inviati: Record<string, unknown>[] = [];
    const receiverCron = {
      ...fixtureReceiver,
      expected_every_seconds: null,
      expected_cron: "0 3 * * *",
      expected_timezone: null,
    };
    server.use(
      http.get("/api/v1/receivers/r1", () => HttpResponse.json(receiverCron)),
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        inviati.push(body);
        return HttpResponse.json({ ...receiverCron, ...body });
      }),
    );
    // Browser in un fuso diverso da UTC: prima il form lo preselezionava e al
    // salvataggio spostava il cron di qualche ora.
    const opzioniVere = Intl.DateTimeFormat.prototype.resolvedOptions;
    const spia = vi
      .spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions")
      .mockImplementation(function (this: Intl.DateTimeFormat) {
        return { ...opzioniVere.call(this), timeZone: "America/New_York" };
      });

    try {
      setRefreshToken("refresh-token-fixture");
      renderReceiverDetail();
      await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
      expect(screen.getByLabelText("Fuso dell'espressione")).toHaveValue("UTC");

      // Solo il nome: la sorveglianza non cambia e non viaggia nella PATCH.
      await user.clear(screen.getByLabelText("Nome"));
      await user.type(screen.getByLabelText("Nome"), "Backup rinominato");
      await user.click(screen.getByRole("button", { name: "Salva" }));
      await waitFor(() => expect(inviati).toHaveLength(1));
      expect(inviati[0]).toMatchObject({ name: "Backup rinominato" });
      for (const campo of [
        "expected_every_seconds",
        "expected_cron",
        "expected_timezone",
        "expected_grace_seconds",
        "missing_severity",
      ]) {
        expect(inviati[0]).not.toHaveProperty(campo);
      }

      // Cambiando la tolleranza la politica si manda intera, col fuso esplicito
      // UTC: lo stesso con cui il backend la valutava prima.
      await user.click(await screen.findByRole("button", { name: "Modifica receiver" }));
      await user.clear(screen.getByLabelText("Tolleranza sul ritardo"));
      await user.type(screen.getByLabelText("Tolleranza sul ritardo"), "45");
      await user.click(screen.getByRole("button", { name: "Salva" }));
      await waitFor(() => expect(inviati).toHaveLength(2));
      expect(inviati[1]).toMatchObject({
        expected_cron: "0 3 * * *",
        expected_timezone: "UTC",
        expected_grace_seconds: 2700,
      });
    } finally {
      spia.mockRestore();
    }
  });

  it("una rinomina manda solo il nome, non i campi che il form non ha toccato", async () => {
    const user = userEvent.setup();
    const inviati: Record<string, unknown>[] = [];
    server.use(
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        inviati.push(body);
        return HttpResponse.json({ ...fixtureReceiver, ...body });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "Backup rinominato");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Un salvataggio con il solo nome non riscrive severity, limiti, exit code
    // e soglia di durata: se un altro admin li ha cambiati, quei valori restano.
    await waitFor(() => expect(inviati).toHaveLength(1));
    expect(inviati[0]).toEqual({ name: "Backup rinominato" });
  });

  it("T-CAP1 il tetto del tenant rifiuta il limite corpo e il motivo resta nel form", async () => {
    const user = userEvent.setup();
    server.use(
      http.patch("/api/v1/receivers/r1", () =>
        HttpResponse.json(
          {
            type: "/problems/unprocessable",
            title: "Unprocessable",
            status: 422,
            detail: "MOTIVO_CAP",
          },
          { status: 422 },
        ),
      ),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    await user.clear(screen.getByLabelText("Limite corpo (byte)"));
    await user.type(screen.getByLabelText("Limite corpo (byte)"), "2048");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Toast e banner dicono entrambi il motivo: si controlla il banner, che resta.
    await waitFor(() =>
      expect(document.querySelector(".error-banner")).toHaveTextContent("MOTIVO_CAP"),
    );
    expect(screen.getByLabelText("Limite corpo (byte)")).toHaveValue(2048);
  });

  it("T-REP2 salvare il receiver ricalcola la prova sulle ultime notifiche", async () => {
    const user = userEvent.setup();
    let ricalcoli = 0;
    server.use(
      http.get("/api/v1/receivers/r1/severity-rules/replay", () => {
        ricalcoli += 1;
        return HttpResponse.json(fixtureSeverityReplay);
      }),
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureReceiver, ...body });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /ultime notifiche/i }));
    await waitFor(() => expect(ricalcoli).toBe(1));

    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    await user.selectOptions(screen.getByLabelText("Severity di default"), "warning");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(ricalcoli).toBe(2));
  });

  it("T-LIM1 rifiuta valori oltre il massimo intero, infiniti o decimali", async () => {
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    const scrivi = async (etichetta: string, valore: string) => {
      await user.clear(screen.getByLabelText(etichetta));
      await user.type(screen.getByLabelText(etichetta), valore);
    };
    // Il tetto del tenant arriva in una richiesta a parte: va sul campo prima di scrivere.
    expect(await screen.findByText(/Massimo per questo tenant/)).toBeInTheDocument();
    await scrivi("Limite corpo (byte)", "2147483648");
    await scrivi("Rate limit (al minuto)", "1e308");
    // 30000 giorni stanno nel campo ma sono 2,59 miliardi di secondi.
    await scrivi("Mi aspetto un invio ogni", "30000");
    await scrivi("Soglia di durata", "1.5");
    await user.selectOptions(screen.getByLabelText("Unità della soglia di durata"), "s");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(screen.getByLabelText("Limite corpo (byte)")).toHaveAccessibleDescription(
      /massimo è 1048576/,
    );
    expect(screen.getByLabelText("Rate limit (al minuto)")).toHaveAccessibleDescription(
      /Troppo grande/,
    );
    expect(screen.getByLabelText("Mi aspetto un invio ogni")).toHaveAccessibleDescription(
      /massimo è 24855 giorni/,
    );
    expect(screen.getByLabelText("Soglia di durata")).toHaveAccessibleDescription(
      /numero intero di secondi/,
    );
    expect(chiamate).toBe(0);
  });

  it("T-LIM2 i decimali che fanno secondi interi vanno bene", async () => {
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
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    await user.clear(screen.getByLabelText("Mi aspetto un invio ogni"));
    await user.type(screen.getByLabelText("Mi aspetto un invio ogni"), "1.5");
    await user.selectOptions(screen.getByLabelText("Unità dell'intervallo atteso"), "h");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).toMatchObject({ expected_every_seconds: 5400 });
  });

  it("T-RATE1 il rate limit vuoto e' un errore, lo zero esplicito vuol dire nessun limite", async () => {
    const user = userEvent.setup();
    const inviati: Record<string, unknown>[] = [];
    server.use(
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        inviati.push(body);
        return HttpResponse.json({ ...fixtureReceiver, ...body });
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    const rate = screen.getByLabelText("Rate limit (al minuto)");
    await user.clear(rate);
    // Il campo resta vuoto: prima diventava 0 da solo e si salvava "nessun
    // limite" senza che nessuno l'avesse scritto.
    expect(rate).toHaveValue(null);
    await user.click(screen.getByRole("button", { name: "Salva" }));
    expect(rate).toHaveAccessibleDescription(/0 se non vuoi nessun limite/);
    expect(inviati).toHaveLength(0);

    await user.type(rate, "0");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(inviati).toHaveLength(1));
    expect(inviati[0]).toMatchObject({ rate_limit_per_min: 0 });
  });

  it("T-INV1 rinomina, stato e slug aggiornano anche gli elenchi dei receiver", async () => {
    const user = userEvent.setup();
    const invalida = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    server.use(
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureReceiver, ...body });
      }),
      http.post("/api/v1/receivers/r1/rotate-slug", () => HttpResponse.json(fixtureReceiver)),
    );
    const chiaviInvalidate = () =>
      invalida.mock.calls.map(([filtro]) => JSON.stringify(filtro?.queryKey));
    const elenchi = [
      JSON.stringify(["receivers", "g1"]),
      JSON.stringify(["group-receivers", "g1"]),
      JSON.stringify(["receivers-all"]),
    ];

    try {
      setRefreshToken("refresh-token-fixture");
      renderReceiverDetail();
      await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

      for (const azione of ["status", "rotate", "rename"] as const) {
        invalida.mockClear();
        if (azione === "status") {
          await user.click(screen.getByRole("button", { name: "Disabilita receiver" }));
          await user.click(
            within(screen.getByRole("dialog")).getByRole("button", { name: "Disabilita receiver" }),
          );
        } else if (azione === "rotate") {
          await user.click(await screen.findByRole("button", { name: "Rigenera slug" }));
          await user.click(
            within(screen.getByRole("dialog")).getByRole("button", { name: "Rigenera slug" }),
          );
        } else {
          await user.click(await screen.findByRole("button", { name: "Modifica receiver" }));
          await user.click(screen.getByRole("button", { name: "Salva" }));
        }
        await waitFor(() => expect(chiaviInvalidate()).toEqual(expect.arrayContaining(elenchi)));
      }
    } finally {
      invalida.mockRestore();
    }
  });

  it("T-INV2 dopo l'eliminazione torna al gruppo del receiver e aggiorna gli elenchi", async () => {
    const user = userEvent.setup();
    const invalida = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    server.use(
      http.delete("/api/v1/receivers/r1", () => new HttpResponse(null, { status: 204 })),
    );

    try {
      setRefreshToken("refresh-token-fixture");
      renderWithProviders(
        <Routes>
          <Route path="/receivers/:id" element={<ReceiverDetailPage />} />
          <Route path="/groups/:id" element={<p>Pagina del gruppo</p>} />
          <Route path="/groups" element={<p>Elenco dei gruppi</p>} />
        </Routes>,
        ["/receivers/r1"],
      );
      await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: "Elimina receiver" }));
      const dialogo = screen.getByRole("dialog");
      await user.type(within(dialogo).getByLabelText(/per confermare/), "Backup notturno");
      await user.click(within(dialogo).getByRole("button", { name: "Elimina receiver" }));

      expect(await screen.findByText("Pagina del gruppo")).toBeInTheDocument();
      const chiavi = invalida.mock.calls.map(([filtro]) => JSON.stringify(filtro?.queryKey));
      expect(chiavi).toEqual(
        expect.arrayContaining([
          JSON.stringify(["receivers", "g1"]),
          JSON.stringify(["group-receivers", "g1"]),
          JSON.stringify(["receivers-all"]),
        ]),
      );
    } finally {
      invalida.mockRestore();
    }
  });
  it("il receiver disabilitato dice cosa succede senza il rosso dell'errore", async () => {
    server.use(
      http.get("/api/v1/receivers/r1", () =>
        HttpResponse.json({ ...fixtureReceiver, status: "disabled", rejected_last_24h: 3 }),
      ),
    );

    renderReceiverDetail();

    const avviso = (await screen.findByText(/Receiver disabilitato:/)).closest("div");
    expect(avviso).toHaveTextContent("Receiver disabilitato: 3 richieste rifiutate");
    expect(avviso).toHaveClass("warning-banner");
    expect(avviso).not.toHaveClass("error-banner");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("i titoli delle card sono h3, come nelle altre pagine", async () => {
    renderReceiverDetail();

    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    expect(screen.getByRole("heading", { level: 3, name: "Configurazione" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Come inviare qui" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "Sorveglianza dell'attesa" }),
    ).toBeInTheDocument();
  });
  it("i select marcati obbligatori portano l'attributo required", async () => {
    const user = userEvent.setup();
    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));

    expect(screen.getByLabelText("Severity di default")).toBeRequired();
    expect(screen.getByLabelText("Attesa")).toBeRequired();
    expect(screen.getByLabelText("Severity dell'assenza")).toBeRequired();
  });

  it("la configurazione dice le severity con le etichette della tabella, non in inglese", async () => {
    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();

    await waitFor(() => expect(campo("Severity di default")).toContain("Info"));
    expect(campo("Severity di default")).not.toMatch(/\binfo\b/);
    expect(campo("Severity per exit code diverso da zero")).toContain("Critica");
    expect(campo("Soglia di durata")).toContain("Errore");
  });

  it("il limite del corpo non va oltre il tetto del tenant, e il campo dice quanto è", async () => {
    const user = userEvent.setup();
    let inviati = 0;
    server.use(
      http.patch("/api/v1/receivers/r1", () => {
        inviati += 1;
        return HttpResponse.json(fixtureReceiver);
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    // Il tetto arriva dal tenant: si aspetta che sia sul campo prima di scrivere.
    expect(await screen.findByText(/Massimo per questo tenant/)).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Limite corpo (byte)"));
    await user.type(screen.getByLabelText("Limite corpo (byte)"), "2000000");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(screen.getByLabelText("Limite corpo (byte)")).toHaveAccessibleDescription(
      /massimo è 1048576/,
    );
    expect(inviati).toBe(0);
  });

  it("un errore dello scaricamento sta fuori dalla riga dei pulsanti dell'intestazione", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/receivers/r1/wrapper-script", () =>
        HttpResponse.json(
          { type: "/problems/internal-error", title: "Internal Server Error", status: 500, detail: "Script non disponibile." },
          { status: 500 },
        ),
      ),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Scarica lo script" }));

    expect((await screen.findAllByText(/Script non disponibile/)).length).toBeGreaterThan(0);
    // Dentro la riga dei pulsanti, il banner andava a capo solo come un pezzo di flex.
    expect(document.querySelector(".page-header-actions .error-banner")).toBeNull();
  });

  it("un limite già salvato sopra il tetto non blocca il salvataggio degli altri campi", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/receivers/r1", () =>
        HttpResponse.json({ ...fixtureReceiver, max_body_bytes: 2_000_000 }),
      ),
      http.patch("/api/v1/receivers/r1", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(fixtureReceiver);
      }),
    );

    setRefreshToken("refresh-token-fixture");
    renderReceiverDetail();
    await waitFor(() => expect(screen.getByText("Slug")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Modifica receiver" }));
    expect(await screen.findByText(/Massimo per questo tenant/)).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "Nuovo nome");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(inviato).toMatchObject({ name: "Nuovo nome" }));
    expect(inviato).not.toHaveProperty("max_body_bytes");
  });
});
