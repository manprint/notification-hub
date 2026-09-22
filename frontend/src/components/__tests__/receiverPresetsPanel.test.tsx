import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import ReceiverPresetsPanel from "../ReceiverPresetsPanel";
import { setRefreshToken } from "../../api/client";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "../../pages/__tests__/testUtils";

function renderPanel() {
  return renderWithProviders(<ReceiverPresetsPanel receiverId="r1" />);
}

describe("ReceiverPresetsPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  it("mostra i preset applicati nell'ordine di valutazione", async () => {
    renderPanel();

    const elenco = await screen.findByRole("list", { name: "Preset applicati" });
    expect(within(elenco).getAllByRole("listitem")).toHaveLength(1);
    expect(elenco.textContent).toContain("Bash generico");
  });

  it("elenca fra i disponibili solo i preset non ancora applicati", async () => {
    renderPanel();

    await waitFor(() => expect(screen.getByLabelText("Applica Backup interni")).toBeInTheDocument());
    // Bash generico e gia applicato: non deve comparire fra le caselle.
    expect(screen.queryByLabelText("Applica Bash generico")).not.toBeInTheDocument();
  });

  it("applicare un preset invia l'elenco completo, non solo il nuovo", async () => {
    const user = userEvent.setup();
    let inviato: unknown = null;
    server.use(
      http.put("/api/v1/receivers/r1/presets", async ({ request }) => {
        inviato = await request.json();
        return HttpResponse.json([]);
      }),
    );
    renderPanel();

    await user.click(await screen.findByLabelText("Applica Backup interni"));
    await waitFor(() => expect(inviato).toEqual({ preset_ids: ["p1", "p2"] }));
  });

  it("togliere un preset lo esclude dall'elenco inviato", async () => {
    const user = userEvent.setup();
    let inviato: unknown = null;
    server.use(
      http.get("/api/v1/receivers/r1/presets", () =>
        HttpResponse.json([
          {
            preset_id: "p1",
            name: "Bash generico",
            description: "",
            builtin_key: "bash-generic",
            position: 0,
            rules_count: 2,
          },
          {
            preset_id: "p2",
            name: "Backup interni",
            description: "",
            builtin_key: null,
            position: 1,
            rules_count: 1,
          },
        ]),
      ),
      http.put("/api/v1/receivers/r1/presets", async ({ request }) => {
        inviato = await request.json();
        return HttpResponse.json([]);
      }),
    );
    renderPanel();

    await waitFor(() => expect(screen.getByText("Backup interni")).toBeInTheDocument());
    const riga = screen.getByText("Bash generico").closest("li")!;
    await user.click(within(riga).getByRole("button", { name: "Togli" }));

    await waitFor(() => expect(inviato).toEqual({ preset_ids: ["p2"] }));
  });

  it("le frecce riordinano i preset applicati", async () => {
    const user = userEvent.setup();
    let inviato: unknown = null;
    server.use(
      http.get("/api/v1/receivers/r1/presets", () =>
        HttpResponse.json([
          {
            preset_id: "p1",
            name: "Bash generico",
            description: "",
            builtin_key: "bash-generic",
            position: 0,
            rules_count: 2,
          },
          {
            preset_id: "p2",
            name: "Backup interni",
            description: "",
            builtin_key: null,
            position: 1,
            rules_count: 1,
          },
        ]),
      ),
      http.put("/api/v1/receivers/r1/presets", async ({ request }) => {
        inviato = await request.json();
        return HttpResponse.json([]);
      }),
    );
    renderPanel();

    await user.click(await screen.findByLabelText("Sposta giù Bash generico"));
    await waitFor(() => expect(inviato).toEqual({ preset_ids: ["p2", "p1"] }));
    expect(screen.getByLabelText("Sposta su Bash generico")).toBeDisabled();
  });

  it("T-PRS1 con l'elenco applicato in errore non si puo applicare niente", async () => {
    let put = 0;
    server.use(
      http.get("/api/v1/receivers/r1/presets", () =>
        HttpResponse.json(
          { type: "/problems/internal-error", title: "Internal Server Error", detail: "boom" },
          { status: 500 },
        ),
      ),
      http.put("/api/v1/receivers/r1/presets", () => {
        put += 1;
        return HttpResponse.json([]);
      }),
    );
    renderPanel();

    // Senza l'elenco applicato, "Applica" manderebbe il solo preset nuovo e
    // staccherebbe gli altri: la casella non c'e' proprio, e l'errore si vede.
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.queryByLabelText("Applica Backup interni")).not.toBeInTheDocument();
    expect(screen.queryByText(/Nessun preset applicato/)).not.toBeInTheDocument();
    expect(put).toBe(0);
  });

  it("T-PRS2 mentre l'elenco applicato carica le azioni non ci sono", async () => {
    let rispondi: () => void = () => undefined;
    server.use(
      http.get("/api/v1/receivers/r1/presets", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json([]);
      }),
    );
    renderPanel();

    expect(await screen.findByText(/Caricamento dei preset applicati/)).toBeInTheDocument();
    // Anche col catalogo gia' arrivato, senza l'elenco applicato non si agisce.
    expect(screen.queryByLabelText("Applica Backup interni")).not.toBeInTheDocument();

    rispondi();
    expect(await screen.findByLabelText("Applica Backup interni")).toBeEnabled();
  });

  it("T-PRS3 mostra anche l'errore del catalogo dei preset", async () => {
    server.use(
      http.get("/api/v1/severity-presets", () =>
        HttpResponse.json(
          { type: "/problems/internal-error", title: "Internal Server Error", detail: "catalogo giu" },
          { status: 500 },
        ),
      ),
    );
    renderPanel();

    expect(await screen.findByText("catalogo giu")).toBeInTheDocument();
  });

  it("il viewer vede i preset applicati ma non li puo cambiare", async () => {
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
    );
    renderPanel();

    await waitFor(() => expect(screen.getByText("Bash generico")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Togli" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Applica Backup interni")).not.toBeInTheDocument();
  });
});
