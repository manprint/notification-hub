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
    expect(await screen.findByText("Silenziato", { selector: "td" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Elimina" }));
    const dialogo = screen.getByRole("dialog");
    await user.type(within(dialogo).getByLabelText(/per confermare/), "Slack #ops");
    await user.click(within(dialogo).getByRole("button", { name: "Elimina canale" }));

    // Il backend ha cancellato l'override a cascata: la riga non resta con
    // l'UUID del canale al posto del nome.
    expect(await screen.findByText(/Nessun override per questo receiver/)).toBeInTheDocument();
    expect(screen.queryByText("Silenziato", { selector: "td" })).not.toBeInTheDocument();
  });

  it("la soglia di un override si legge come il badge della severity", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    server.use(
      http.get("/api/v1/receivers/r1/channels", () =>
        HttpResponse.json([
          { id: "o2", receiver_id: "r1", channel_id: "c1", mode: "override", min_severity: "critical" },
        ]),
      ),
    );
    renderWithProviders(<ChannelsPage />);

    await user.selectOptions(
      await screen.findByLabelText(/^receiver$/i),
      await screen.findByRole("option", { name: "Server Produzione / Backup notturno" }),
    );
    const cella = (
      await screen.findByText("Soglia sostituita", { selector: "td" })
    ).closest("tr") as HTMLElement;
    expect(within(cella).getByText("Critica")).toHaveClass("severity-badge", "severity-critical");
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

  it("T-CH4 la modifica non si chiude con Esc mentre il salvataggio è in corso", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    let rispondi: () => void = () => undefined;
    server.use(
      http.patch("/api/v1/channels/c1", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json({});
      }),
    );
    renderWithProviders(<ChannelsPage />);

    await user.click(await screen.findByRole("button", { name: "Modifica" }));
    const dialogo = await screen.findByRole("dialog");
    await user.click(within(dialogo).getByRole("button", { name: "Salva" }));
    await waitFor(() =>
      expect(within(dialogo).getByRole("button", { name: "Salvataggio…" })).toBeInTheDocument(),
    );
    await user.keyboard("{Escape}");

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: "Annulla" })).toBeDisabled();
    rispondi();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("T-CH5 un'eliminazione rifiutata lascia il dialogo aperto con l'errore", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    server.use(
      http.delete("/api/v1/channels/c1", () =>
        HttpResponse.json(
          { type: "/problems/conflict", title: "Conflict", status: 409, detail: "Canale in uso." },
          { status: 409 },
        ),
      ),
    );
    renderWithProviders(<ChannelsPage />);

    await user.click(await screen.findByRole("button", { name: "Elimina" }));
    const dialogo = screen.getByRole("dialog");
    await user.type(within(dialogo).getByLabelText(/per confermare/), "Slack #ops");
    await user.click(within(dialogo).getByRole("button", { name: "Elimina canale" }));

    expect(await within(dialogo).findByText(/Canale in uso/)).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("T-CH6 il webhook di esempio segue il tipo, e il tipo è obbligatorio", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<ChannelsPage />);

    const tipo = await screen.findByLabelText(/^tipo$/i);
    const webhook = screen.getByLabelText(/Webhook URL/);
    expect(tipo).toBeRequired();
    expect(webhook).toHaveAttribute("placeholder", "https://hooks.slack.com/services/…");

    await user.selectOptions(tipo, "google_chat");
    expect(webhook).toHaveAttribute("placeholder", "https://chat.googleapis.com/v1/spaces/…");
  });

  it("T-CH7 lo stato del canale si scrive con la maiuscola come le altre etichette", async () => {
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<ChannelsPage />);

    expect(await screen.findByText("Attivo")).toHaveClass("status-pill");
    expect(screen.queryByText("attivo")).not.toBeInTheDocument();
  });

  it("T-CH8 se la lista dei canali non si carica non dice «nessun canale configurato»", async () => {
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.get("/api/v1/channels", () =>
        HttpResponse.json(
          { type: "/problems/internal", title: "Internal", status: 500, detail: "Giù." },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<ChannelsPage />);

    expect(
      await screen.findByText("Elenco non disponibile per un errore di caricamento."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Nessun canale configurato.")).not.toBeInTheDocument();
  });

  it("T-CH9 gli override di un receiver in caricamento non dicono «nessun override»", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    let rispondi: () => void = () => undefined;
    server.use(
      http.get("/api/v1/receivers/r1/channels", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<ChannelsPage />);

    await user.selectOptions(
      await screen.findByLabelText(/^receiver$/i),
      await screen.findByRole("option", { name: "Server Produzione / Backup notturno" }),
    );
    expect(await screen.findByText("Caricamento…")).toBeInTheDocument();
    expect(screen.queryByText(/Nessun override per questo receiver/)).not.toBeInTheDocument();
    rispondi();
    expect(await screen.findByText(/Nessun override per questo receiver/)).toBeInTheDocument();
  });
});

describe("ChannelsPage moduli e severity", () => {
  it("la tendina della soglia dell'override usa le etichette della severity, non i valori grezzi", async () => {
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<ChannelsPage />);

    const soglia = await screen.findByLabelText("Soglia minima");
    expect(within(soglia).getByRole("option", { name: "Critica" })).toBeInTheDocument();
    expect(within(soglia).queryByRole("option", { name: "critical" })).not.toBeInTheDocument();
  });

  it("creare un canale senza nome mostra il messaggio in italiano e non invia nulla", async () => {
    setRefreshToken("refresh-token-fixture");
    let inviati = 0;
    server.use(
      http.post("/api/v1/channels", () => {
        inviati += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ChannelsPage />);

    await user.click(await screen.findByRole("button", { name: "Crea canale" }));

    expect(await screen.findByText("Il nome del canale è obbligatorio.")).toBeInTheDocument();
    expect(inviati).toBe(0);
  });

  it("modificare un canale senza nome mostra il messaggio in italiano e non invia nulla", async () => {
    setRefreshToken("refresh-token-fixture");
    let inviati = 0;
    server.use(
      http.patch("/api/v1/channels/c1", () => {
        inviati += 1;
        return HttpResponse.json({});
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ChannelsPage />);

    await user.click(await screen.findByRole("button", { name: "Modifica" }));
    const dialogo = await screen.findByRole("dialog");
    await user.clear(within(dialogo).getByLabelText("Nome"));
    await user.click(within(dialogo).getByRole("button", { name: "Salva" }));

    expect(
      await within(dialogo).findByText("Il nome del canale è obbligatorio."),
    ).toBeInTheDocument();
    expect(inviati).toBe(0);
  });
});
