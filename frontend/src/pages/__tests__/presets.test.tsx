import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import PresetsPage from "../PresetsPage";
import { setRefreshToken } from "../../api/client";
import { server } from "../../api/mocks/server";
import { fixturePresetCatalog, fixturePresets } from "../../api/mocks/handlers";
import { renderWithProviders } from "./testUtils";

function renderPage() {
  return renderWithProviders(<PresetsPage />);
}

describe("PresetsPage", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture"); // fixtureMe ha ruolo owner
  });

  it("elenca i preset distinguendo predefiniti e personalizzati", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const predefinito = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    expect(within(predefinito).getByText("predefinito")).toBeInTheDocument();
    expect(within(predefinito).getByText(/applicato a 3 receiver/)).toBeInTheDocument();

    const personalizzato = screen.getByText("Backup interni").closest<HTMLElement>(".card")!;
    expect(within(personalizzato).getByText("personalizzato")).toBeInTheDocument();
  });

  it("propone l'installazione dei soli preset del catalogo non ancora installati", async () => {
    const user = userEvent.setup();
    let chiamato = false;
    server.use(
      http.post("/api/v1/severity-presets/sync-builtin", () => {
        chiamato = true;
        return HttpResponse.json({ installed: ["rclone"], already_present: ["bash-generic"] });
      }),
    );
    renderPage();

    const bottone = await screen.findByRole("button", { name: /Installa i 1 preset mancanti/ });
    // Solo rclone: bash-generic risulta gia installato nel catalogo.
    expect(screen.getByText(/Sincronizzazioni con rclone/)).toBeInTheDocument();
    expect(screen.queryByText(/Errori comuni di shell.*installato/)).not.toBeInTheDocument();

    await user.click(bottone);
    await waitFor(() => expect(chiamato).toBe(true));
    expect(await screen.findByText(/Preset installati: rclone/)).toBeInTheDocument();
  });

  it("non propone nulla quando il catalogo e tutto installato", async () => {
    server.use(
      http.get("/api/v1/severity-presets/catalog", () =>
        HttpResponse.json(fixturePresetCatalog.map((v) => ({ ...v, installed: true }))),
      ),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /preset mancanti/ })).not.toBeInTheDocument();
  });

  it("mostra le regole del preset nell'ordine di valutazione", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Mostra regole" }));

    await waitFor(() =>
      expect(screen.getByText("No space left on device")).toBeInTheDocument(),
    );
    const righe = within(card).getAllByRole("row").slice(1);
    expect(righe[0].textContent).toContain("No space left on device");
    expect(within(righe[1]).getByLabelText("Attiva Permission denied")).not.toBeChecked();
  });

  it("le frecce inviano il nuovo ordine delle regole del preset", async () => {
    const user = userEvent.setup();
    let inviato: unknown = null;
    server.use(
      http.put("/api/v1/severity-presets/p1/rules/order", async ({ request }) => {
        inviato = await request.json();
        return HttpResponse.json([]);
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Mostra regole" }));

    await user.click(await screen.findByLabelText("Sposta giù No space left on device"));
    await waitFor(() => expect(inviato).toEqual({ rule_ids: ["pr2", "pr1"] }));
  });

  it("la nuova regola del preset non chiede la priorita", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/severity-presets/p1/rules", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Mostra regole" }));

    const campi = await within(card).findAllByLabelText("Pattern");
    await user.type(campi[campi.length - 1], "PANIC");
    await user.click(within(card).getByRole("button", { name: "Aggiungi regola" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).not.toHaveProperty("priority");
    expect(inviato).toMatchObject({ pattern: "PANIC" });
  });

  it("il ripristino e offerto solo sui preset predefiniti", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const predefinito = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    const personalizzato = screen.getByText("Backup interni").closest<HTMLElement>(".card")!;

    expect(
      within(predefinito).getByRole("button", { name: /Ripristina i valori predefiniti/ }),
    ).toBeInTheDocument();
    expect(
      within(personalizzato).queryByRole("button", { name: /Ripristina/ }),
    ).not.toBeInTheDocument();
  });

  it("il nome duplicato resta modificabile invece di sparire", async () => {
    const user = userEvent.setup();
    server.use(
      http.patch("/api/v1/severity-presets/p1", () =>
        HttpResponse.json(
          {
            type: "/problems/conflict",
            title: "Conflict",
            status: 409,
            detail: "A preset named 'Backup interni' already exists.",
          },
          { status: 409 },
        ),
      ),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Rinomina" }));
    await user.click(within(card).getByRole("button", { name: "Salva" }));

    expect(await within(card).findByText(/already exists/)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Salva" })).toBeInTheDocument();
  });

  it("T-PST1 l'esito dell'installazione si vede anche se la scheda sparisce", async () => {
    const user = userEvent.setup();
    let installati = false;
    server.use(
      http.post("/api/v1/severity-presets/sync-builtin", () => {
        installati = true;
        return HttpResponse.json({ installed: ["rclone"], already_present: ["bash-generic"] });
      }),
      // Dopo l'installazione il catalogo non ha piu' mancanti: la scheda
      // "Preset predefiniti non ancora installati" smonta.
      http.get("/api/v1/severity-presets/catalog", () =>
        HttpResponse.json(
          fixturePresetCatalog.map((v) => ({ ...v, installed: installati || v.installed })),
        ),
      ),
    );
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Installa i 1 preset mancanti/ }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /preset mancanti/ })).not.toBeInTheDocument(),
    );
    expect(await screen.findByText(/Preset installati: rclone/)).toBeInTheDocument();
  });

  it("T-PST2 Rinomina riparte dal preset attuale, Annulla scarta la bozza", async () => {
    const user = userEvent.setup();
    let descrizione = fixturePresets[0].description;
    server.use(
      http.get("/api/v1/severity-presets", () =>
        HttpResponse.json([{ ...fixturePresets[0], description: descrizione }, fixturePresets[1]]),
      ),
      http.post("/api/v1/severity-presets/p1/reset", () => {
        descrizione = "Descrizione ripristinata.";
        return HttpResponse.json({});
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;

    // Bozza scritta e poi annullata: riaprendo non deve ricomparire.
    await user.click(within(card).getByRole("button", { name: "Rinomina" }));
    await user.clear(within(card).getByLabelText("Nome"));
    await user.type(within(card).getByLabelText("Nome"), "Bozza scartata");
    await user.click(within(card).getByRole("button", { name: "Annulla" }));
    await user.click(within(card).getByRole("button", { name: "Rinomina" }));
    expect(within(card).getByLabelText("Nome")).toHaveValue("Bash generico");
    await user.click(within(card).getByRole("button", { name: "Annulla" }));

    // Dopo il ripristino la bozza riparte dai valori nuovi, non da quelli letti
    // al primo caricamento della pagina.
    await user.click(within(card).getByRole("button", { name: /Ripristina i valori predefiniti/ }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Ripristina" }));
    expect(await within(card).findByText("Descrizione ripristinata.")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Rinomina" }));
    expect(within(card).getByLabelText("Descrizione")).toHaveValue("Descrizione ripristinata.");
  });

  it("T-PST3 il nome si salva senza spazi e non puo' essere vuoto", async () => {
    const user = userEvent.setup();
    const inviati: Record<string, unknown>[] = [];
    server.use(
      http.patch("/api/v1/severity-presets/p1", async ({ request }) => {
        inviati.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(fixturePresets[0]);
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Rinomina" }));

    await user.clear(within(card).getByLabelText("Nome"));
    await user.type(within(card).getByLabelText("Nome"), "   ");
    await user.click(within(card).getByRole("button", { name: "Salva" }));
    expect(await within(card).findByText(/Il nome del preset è obbligatorio/)).toBeInTheDocument();
    expect(inviati).toHaveLength(0);

    await user.clear(within(card).getByLabelText("Nome"));
    await user.type(within(card).getByLabelText("Nome"), "  Backup interni ");
    await user.click(within(card).getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(inviati).toHaveLength(1));
    expect(inviati[0]).toMatchObject({ name: "Backup interni" });
  });

  it("T-PST4 le frecce delle regole restano ferme finche' un riordino e' in volo", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    let sblocca: () => void = () => undefined;
    server.use(
      http.put("/api/v1/severity-presets/p1/rules/order", async () => {
        chiamate += 1;
        await new Promise<void>((resolve) => {
          sblocca = resolve;
        });
        return HttpResponse.json([]);
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Mostra regole" }));

    await user.click(await screen.findByLabelText("Sposta giù No space left on device"));
    await waitFor(() => expect(chiamate).toBe(1));
    expect(screen.getByLabelText("Sposta su Permission denied")).toBeDisabled();
    await user.click(screen.getByLabelText("Sposta su Permission denied"));

    sblocca();
    await waitFor(() =>
      expect(screen.getByLabelText("Sposta giù No space left on device")).toBeEnabled(),
    );
    expect(chiamate).toBe(1);
  });

  it("il member vede i preset ma non li puo modificare", async () => {
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
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Rinomina" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crea preset" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /preset mancanti/ })).not.toBeInTheDocument();
  });
  it("T-PST5 Ripristina chiede conferma: annullando non tocca il preset", async () => {
    const user = userEvent.setup();
    const chiamate: string[] = [];
    server.use(
      http.post("/api/v1/severity-presets/p1/reset", () => {
        chiamate.push("reset");
        return HttpResponse.json({});
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: /Ripristina i valori predefiniti/ }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/regole attuali/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Annulla" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(chiamate).toHaveLength(0);
  });

  it("T-PST6 eliminare un preset tiene il dialogo occupato finché la richiesta risponde", async () => {
    const user = userEvent.setup();
    let rispondi: () => void = () => undefined;
    let chiamate = 0;
    server.use(
      http.delete("/api/v1/severity-presets/p2", async () => {
        chiamate += 1;
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Backup interni").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Elimina preset" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Digita/), "Backup interni");
    await user.click(within(dialog).getByRole("button", { name: "Elimina preset" }));

    expect(within(dialog).getByRole("button", { name: "Elimina preset" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Annulla" })).toBeDisabled();
    rispondi();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(chiamate).toBe(1);
  });

  it("T-PST7 la lista delle regole non dice 'non ha ancora regole' mentre si carica o dopo un errore", async () => {
    const user = userEvent.setup();
    let rispondi: () => void = () => undefined;
    server.use(
      http.get("/api/v1/severity-presets/p1", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json({ ...fixturePresets[0], rules: [] });
      }),
    );
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Mostra regole" }));

    expect(await within(card).findByText("Caricamento delle regole…")).toBeInTheDocument();
    expect(within(card).queryByText(/non ha ancora regole/)).not.toBeInTheDocument();
    rispondi();
    expect(await within(card).findByText(/non ha ancora regole/)).toBeInTheDocument();
  });

  it("T-PST8 la regola ha etichette visibili e l'errore è collegato al campo", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    const card = screen.getByText("Bash generico").closest<HTMLElement>(".card")!;
    await user.click(within(card).getByRole("button", { name: "Mostra regole" }));

    const pattern = await within(card).findByLabelText("Pattern");
    expect(within(card).getByLabelText("Severity", { selector: "select" })).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Aggiungi regola" }));

    const messaggio = await within(card).findByText("Il pattern è obbligatorio.");
    expect(pattern).toHaveAttribute("aria-invalid", "true");
    expect(pattern).toHaveAttribute("aria-describedby", messaggio.id);
  });
});
