import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import PresetsPage from "../PresetsPage";
import { setRefreshToken } from "../../api/client";
import { server } from "../../api/mocks/server";
import { fixturePresetCatalog } from "../../api/mocks/handlers";
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

    const campi = await within(card).findAllByLabelText("Pattern RE2 del preset");
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
});
