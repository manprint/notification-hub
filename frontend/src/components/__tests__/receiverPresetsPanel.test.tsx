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
