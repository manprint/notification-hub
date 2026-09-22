import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import ChannelsPage from "../ChannelsPage";
import { setRefreshToken } from "../../api/client";
import { fixtureChannels, fixtureReceiver } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

const FULL_WEBHOOK_URL = "https://hooks.slack.com/services/T0/B0/X0";

describe("ChannelsPage", () => {
  it("T-UI15 test_webhook_mai_in_chiaro: l'URL completa non compare in nessun testo né in alcun value", async () => {
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<ChannelsPage />);

    await waitFor(() => {
      expect(screen.getAllByText("Slack #ops").length).toBeGreaterThan(0);
    });

    expect(document.body.textContent).not.toContain(FULL_WEBHOOK_URL);
    for (const input of Array.from(document.querySelectorAll("input"))) {
      expect((input as HTMLInputElement).value).not.toContain(FULL_WEBHOOK_URL);
    }
  });

  it("T-UI16 test_mute_nasconde_la_soglia: scegliendo mute il campo min_severity sparisce", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<ChannelsPage />);

    await waitFor(() => {
      expect(screen.getAllByText("Slack #ops").length).toBeGreaterThan(0);
    });

    expect(screen.getByLabelText(/soglia minima/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/modalità/i), "mute");

    expect(screen.queryByLabelText(/soglia minima/i)).not.toBeInTheDocument();
  });
});

describe("ChannelsPage override", () => {
  it("il receiver si sceglie da un elenco, non digitando un UUID a mano", async () => {
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<ChannelsPage />);

    const receiverField = await screen.findByLabelText(/^receiver$/i);
    expect(receiverField.tagName).toBe("SELECT");
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: "Server Produzione / Backup notturno" }),
      ).toBeInTheDocument();
    });
  });

  it("T-CH1 due receiver con lo stesso nome si distinguono dal gruppo", async () => {
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.get("/api/v1/receivers", () =>
        HttpResponse.json([
          { ...fixtureReceiver, id: "ra", name: "backup", group_id: "g1" },
          { ...fixtureReceiver, id: "rb", name: "backup", group_id: "g2" },
        ]),
      ),
    );
    renderWithProviders(<ChannelsPage />);

    const campo = await screen.findByLabelText(/^receiver$/i);
    await waitFor(() => {
      const etichette = within(campo)
        .getAllByRole("option")
        .map((o) => o.textContent);
      expect(etichette).toEqual(["Scegli un receiver", "Backup / backup", "Server Produzione / backup"]);
    });
  });

  it("T-CH2 eliminare un canale aggiorna gli override gia' aperti", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    let eliminato = false;
    server.use(
      http.get("/api/v1/channels", () => HttpResponse.json(eliminato ? [] : fixtureChannels)),
      http.delete("/api/v1/channels/c1", () => {
        eliminato = true;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("/api/v1/receivers/r1/channels", () =>
        HttpResponse.json(
          eliminato
            ? []
            : [{ id: "o1", receiver_id: "r1", channel_id: "c1", mode: "mute", min_severity: null }],
        ),
      ),
    );
    renderWithProviders(<ChannelsPage />);

    await user.selectOptions(
      await screen.findByLabelText(/^receiver$/i),
      await screen.findByRole("option", { name: "Server Produzione / Backup notturno" }),
    );
    expect(await screen.findByText("silenziato")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Elimina" }));
    const dialogo = screen.getByRole("dialog");
    await user.type(within(dialogo).getByLabelText(/per confermare/), "Slack #ops");
    await user.click(within(dialogo).getByRole("button", { name: "Elimina canale" }));

    // Il backend ha cancellato l'override a cascata: la riga non resta con
    // l'UUID del canale al posto del nome.
    expect(await screen.findByText(/Nessun override per questo receiver/)).toBeInTheDocument();
    expect(screen.queryByText("silenziato")).not.toBeInTheDocument();
  });

  it("T-CH3 cambiando gruppo lo stato della riga salvata non passa al gruppo nuovo", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/groups/g1/channels", () =>
        HttpResponse.json(
          { type: "/problems/conflict", title: "Conflict", status: 409, detail: "Gia' collegato." },
          { status: 409 },
        ),
      ),
    );
    renderWithProviders(<ChannelsPage />);

    const gruppo = await screen.findByLabelText("Gruppo");
    await user.selectOptions(gruppo, await screen.findByRole("option", { name: "Server Produzione" }));
    await user.selectOptions(await screen.findByLabelText("Soglia di Slack #ops"), "error");
    expect(await screen.findByText("Non salvato")).toBeInTheDocument();

    await user.selectOptions(gruppo, "Backup");
    await waitFor(() => expect(screen.getByLabelText("Soglia di Slack #ops")).toHaveValue(""));
    expect(screen.queryByText("Non salvato")).not.toBeInTheDocument();
  });

  it("non propone tipi di canale che il backend rifiuta", async () => {
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<ChannelsPage />);

    const typeField = await screen.findByLabelText(/tipo/i);
    const values = Array.from(typeField.querySelectorAll("option")).map((o) => o.value);
    expect(values).toEqual(["slack", "google_chat"]);
  });
});
