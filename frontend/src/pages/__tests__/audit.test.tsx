import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import AuditNotificationStatusPage from "../AuditNotificationStatusPage";
import AuditPage from "../AuditPage";
import { fixtureAuditEvents, filterAuditEvents } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

/** Il giorno di oggi come lo scrive un <input type="date">, nel fuso locale. */
function oggi(adesso: Date): string {
  const mese = String(adesso.getMonth() + 1).padStart(2, "0");
  const giorno = String(adesso.getDate()).padStart(2, "0");
  return `${adesso.getFullYear()}-${mese}-${giorno}`;
}

/** Un evento avvenuto adesso, servito con la stessa semantica del backend:
 *  `occurred_at >= from` e `occurred_at <= to`, confrontati come istanti. */
function serviEventoDiOggi(path: string, adesso: Date, richieste: URLSearchParams[]) {
  const evento = { ...fixtureAuditEvents[0], id: "oggi", occurred_at: adesso.toISOString() };
  server.use(
    http.get(path, ({ request }) => {
      const params = new URL(request.url).searchParams;
      richieste.push(params);
      const events = filterAuditEvents([evento], params, false);
      if (events === null) return HttpResponse.json({ detail: "bad" }, { status: 422 });
      return HttpResponse.json({ events, next_cursor: null });
    }),
  );
}

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

  it("la colonna Chi stampa il ruolo in italiano, non il codice", async () => {
    renderWithProviders(<AuditPage />);
    await waitFor(() => expect(screen.getByText("mario@acme.test")).toBeInTheDocument());

    // La prima riga della fixture è di un operatore: il ruolo è la sua etichetta.
    const chi = cella(1, "Chi");
    expect(within(chi).getByText(/Operatore/)).toBeInTheDocument();
    expect(chi.textContent).not.toMatch(/\bmember\b/);
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

  it("la tendina dei tipi di risorsa comprende tutto cio' che il backend registra", async () => {
    renderWithProviders(<AuditPage />);

    const tendina = await screen.findByLabelText("Tipo di risorsa");
    const valori = within(tendina)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    // Le quattro che la lista scritta a mano aveva perso.
    expect(valori).toEqual(
      expect.arrayContaining([
        "group_channel_binding",
        "receiver_channel_override",
        "severity_preset_rule",
        "receiver_severity_preset",
      ]),
    );
    expect(within(tendina).getByRole("option", { name: "Regola di preset" })).toBeInTheDocument();
  });

  it("Da = A = oggi comprende un evento di oggi", async () => {
    const adesso = new Date();
    const giorno = oggi(adesso);
    const richieste: URLSearchParams[] = [];
    serviEventoDiOggi("/api/v1/audit/events", adesso, richieste);

    renderWithProviders(<AuditPage />, [`/settings/audit?from=${giorno}&to=${giorno}`]);

    // Col giorno nudo il backend leggeva "A" come la mezzanotte con cui il
    // giorno comincia, e l'evento di oggi restava fuori.
    expect(await screen.findByText("mario@acme.test")).toBeInTheDocument();
    const params = richieste[richieste.length - 1];
    const offset = /[+-]\d{2}:\d{2}$/;
    expect(params.get("from")).toMatch(offset);
    expect(params.get("to")).toMatch(offset);
    const [anno, mese, data] = giorno.split("-").map(Number);
    expect(new Date(params.get("from") as string).getTime()).toBe(
      new Date(anno, mese - 1, data, 0, 0, 0, 0).getTime(),
    );
    expect(new Date(params.get("to") as string).getTime()).toBe(
      new Date(anno, mese - 1, data, 23, 59, 59, 999).getTime(),
    );
    // Il campo data continua a mostrare il giorno scelto.
    expect(screen.getByLabelText("Da")).toHaveValue(giorno);
    expect(screen.getByLabelText("A")).toHaveValue(giorno);
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

  it("la colonna Chi stampa il ruolo in italiano, non il codice", async () => {
    renderWithProviders(<AuditNotificationStatusPage />);
    await screen.findByText("operazione in blocco");

    const chi = cella(1, "Chi");
    expect(within(chi).getByText(/Operatore/)).toBeInTheDocument();
    expect(chi.textContent).not.toMatch(/\bmember\b/);
  });

  // Il commit dfdda46d aveva sostituito resource_label con il solo "Apri", per
  // non stampare in tabella il corpo del messaggio. Ma resource_label e' la
  // fotografia congelata della notifica (spec 9.6, righe autosufficienti):
  // senza, una notifica purgata diventava una riga senza oggetto. Ora il testo
  // torna, accorciato, e "Apri" resta finche' la notifica esiste.
  it("la notifica si riconosce dalla sua fotografia, e «Apri» porta al dettaglio", async () => {
    renderWithProviders(<AuditNotificationStatusPage />);
    await screen.findByText("operazione in blocco");

    const notifica = cella(1, "Notifica");
    expect(within(notifica).getByText("Backup notturno fallito")).toBeInTheDocument();
    expect(within(notifica).getByRole("link", { name: "Apri" })).toHaveAttribute(
      "href",
      "/notifications/n1",
    );
  });

  it("un'etichetta lunga non allarga la tabella: accorciata, intera nel title", async () => {
    const lunga = ("Backup FALLITO: " + "disco pieno su /var ".repeat(12)).trimEnd();
    server.use(
      http.get("/api/v1/audit/notification-status", () =>
        HttpResponse.json({
          events: [{ ...fixtureAuditEvents[0], resource_label: lunga }],
          next_cursor: null,
        }),
      ),
    );
    renderWithProviders(<AuditNotificationStatusPage />);
    await screen.findByText("mario@acme.test");

    const testo = within(cella(1, "Notifica")).getByTitle(lunga);
    expect(testo.textContent?.length).toBeLessThanOrEqual(81);
    expect(testo.textContent?.endsWith("…")).toBe(true);
  });

  it("una notifica purgata resta leggibile, ma senza un link che porterebbe a un 404", async () => {
    // Dopo la purge il backend non risolve piu' la posizione
    // (services/audit_location.py): receiver e gruppo tornano nulli.
    server.use(
      http.get("/api/v1/audit/notification-status", () =>
        HttpResponse.json({
          events: [
            {
              ...fixtureAuditEvents[0],
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
    renderWithProviders(<AuditNotificationStatusPage />);
    await screen.findByText("mario@acme.test");

    const notifica = cella(1, "Notifica");
    expect(within(notifica).getByText("Backup notturno fallito")).toBeInTheDocument();
    expect(within(notifica).queryByRole("link", { name: "Apri" })).not.toBeInTheDocument();
    expect(within(notifica).getByText(/non più presente/)).toBeInTheDocument();
  });

  it("le date scelte arrivano all'API e all'export come giorni interi locali", async () => {
    const adesso = new Date();
    const giorno = oggi(adesso);
    const richieste: URLSearchParams[] = [];
    serviEventoDiOggi("/api/v1/audit/notification-status", adesso, richieste);
    const esportazioni: URLSearchParams[] = [];
    server.use(
      http.get("/api/v1/audit/export", ({ request }) => {
        esportazioni.push(new URL(request.url).searchParams);
        return HttpResponse.text("occurred_at,actor_email\r\n2026-09-22,però@acme.test\r\n", {
          headers: {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": 'attachment; filename="audit-oggi.csv"',
          },
        });
      }),
    );
    const createObjectURL = vi.fn((_blob: Blob) => "blob:audit");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    const cliccate: Array<{ file: string; connessa: boolean }> = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        cliccate.push({ file: this.download, connessa: this.isConnected });
      });

    try {
      const user = userEvent.setup();
      renderWithProviders(<AuditNotificationStatusPage />);
      await screen.findByLabelText("Da");
      fireEvent.change(screen.getByLabelText("Da"), { target: { value: giorno } });
      fireEvent.change(screen.getByLabelText("A"), { target: { value: giorno } });

      expect(await screen.findByText("mario@acme.test")).toBeInTheDocument();
      const [anno, mese, data] = giorno.split("-").map(Number);
      const fine = new Date(anno, mese - 1, data, 23, 59, 59, 999).getTime();
      await waitFor(() => {
        const ultima = richieste[richieste.length - 1];
        expect(new Date(ultima.get("to") as string).getTime()).toBe(fine);
      });

      await user.click(screen.getByRole("button", { name: "Esporta CSV" }));
      await waitFor(() => expect(cliccate).toHaveLength(1));

      // L'export usa gli stessi estremi della tabella.
      const esportazione = esportazioni[0];
      expect(esportazione.get("notification_status_only")).toBe("true");
      expect(new Date(esportazione.get("from") as string).getTime()).toBe(
        new Date(anno, mese - 1, data, 0, 0, 0, 0).getTime(),
      );
      expect(new Date(esportazione.get("to") as string).getTime()).toBe(fine);

      // Il file comincia col BOM UTF-8 (EF BB BF): senza, Excel in italiano
      // apre il CSV come Windows-1252 e rovina gli accenti.
      const blob = createObjectURL.mock.calls[0][0];
      const byte = await new Promise<Uint8Array>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
        reader.readAsArrayBuffer(blob);
      });
      expect(Array.from(byte.slice(0, 3))).toEqual([0xef, 0xbb, 0xbf]);
      expect(blob.type).toContain("text/csv");

      // Scaricamento che regge su Firefox e Safari: ancora nel documento al
      // click, URL revocato piu' tardi e non subito.
      expect(cliccate[0]).toEqual({ file: "audit-oggi.csv", connessa: true });
      expect(revokeObjectURL).not.toHaveBeenCalled();
    } finally {
      clickSpy.mockRestore();
    }
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
