// Collegamento gruppo-canale: e' la tabella che decide chi viene svegliato di
// notte. Era il componente meno coperto del frontend (2,35%): un errore qui non
// da' errore, smette semplicemente di arrivare qualcosa.
//
// Le tre transizioni che contano, e che il componente distingue da solo perche'
// l'API ha due verbi diversi:
//   non collegato -> collegato        POST   (crea il binding)
//   collegato      -> soglia diversa  PUT    (aggiorna, non duplica)
//   collegato      -> non collegato   DELETE (slega)

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import ChannelBindings from "../ChannelBindings";
import { setRefreshToken } from "../../api/client";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "../../pages/__tests__/testUtils";
import type { DeliveryChannelOut } from "../../api/types";

const GROUP_ID = "g1";

const canali: DeliveryChannelOut[] = [
  {
    id: "c1",
    name: "Slack #ops",
    type: "slack",
    webhook_hint: "hooks.slack.com/…/X0",
    enabled: true,
    last_success_at: null,
    last_error_at: null,
    last_error: null,
  },
  {
    id: "c2",
    name: "Chat SRE",
    type: "google_chat",
    webhook_hint: "chat.googleapis.com/…/Y0",
    enabled: true,
    last_success_at: null,
    last_error_at: null,
    last_error: null,
  },
];

function renderBindings(bindings: unknown[] = []) {
  server.use(
    http.get(`/api/v1/groups/${GROUP_ID}/channels`, () => HttpResponse.json(bindings)),
  );
  return renderWithProviders(<ChannelBindings groupId={GROUP_ID} channels={canali} />);
}

function rigaDi(nome: string): HTMLElement {
  return screen.getByText(new RegExp(nome)).closest("tr")!;
}

describe("ChannelBindings", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  it("mostra la soglia dei canali collegati e «Non collegato» per gli altri", async () => {
    renderBindings([
      { id: "b1", group_id: GROUP_ID, channel_id: "c1", min_severity: "error", enabled: true },
    ]);

    await waitFor(() => {
      expect(within(rigaDi("Slack #ops")).getByRole("combobox")).toHaveValue("error");
    });
    expect(within(rigaDi("Chat SRE")).getByRole("combobox")).toHaveValue("");
    // Il tipo del canale si legge in chiaro: Slack e Google Chat formattano in
    // modo diverso, e sbagliare canale e' un errore che si scopre tardi.
    expect(screen.getByText(/Chat SRE \(Google Chat\)/)).toBeInTheDocument();
  });

  it("collegare un canale non collegato usa POST col channel_id", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    let metodo = "";
    server.use(
      http.post(`/api/v1/groups/${GROUP_ID}/channels`, async ({ request }) => {
        metodo = "POST";
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderBindings();
    await waitFor(() => expect(screen.getByText(/Slack #ops/)).toBeInTheDocument());

    await user.selectOptions(within(rigaDi("Slack #ops")).getByRole("combobox"), "critical");

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(metodo).toBe("POST");
    expect(inviato).toEqual({ channel_id: "c1", min_severity: "critical" });
  });

  it("cambiare la soglia di un canale gia collegato usa PUT, non un secondo POST", async () => {
    const user = userEvent.setup();
    const chiamate: string[] = [];
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.post(`/api/v1/groups/${GROUP_ID}/channels`, () => {
        chiamate.push("POST");
        return HttpResponse.json({}, { status: 201 });
      }),
      http.put(`/api/v1/groups/${GROUP_ID}/channels/c1`, async ({ request }) => {
        chiamate.push("PUT");
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({});
      }),
    );

    renderBindings([
      { id: "b1", group_id: GROUP_ID, channel_id: "c1", min_severity: "error", enabled: true },
    ]);
    await waitFor(() => {
      expect(within(rigaDi("Slack #ops")).getByRole("combobox")).toHaveValue("error");
    });

    await user.selectOptions(within(rigaDi("Slack #ops")).getByRole("combobox"), "warning");

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(chiamate).toEqual(["PUT"]);
    // `enabled: true` esplicito: abbassare la soglia su un binding spento deve
    // anche riaccenderlo, altrimenti la modifica non ha nessun effetto visibile.
    expect(inviato).toEqual({ min_severity: "warning", enabled: true });
  });

  it("«Non collegato» slega il canale con DELETE", async () => {
    const user = userEvent.setup();
    let chiamato = "";
    server.use(
      http.delete(`/api/v1/groups/${GROUP_ID}/channels/c1`, () => {
        chiamato = "DELETE";
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderBindings([
      { id: "b1", group_id: GROUP_ID, channel_id: "c1", min_severity: "error", enabled: true },
    ]);
    await waitFor(() => {
      expect(within(rigaDi("Slack #ops")).getByRole("combobox")).toHaveValue("error");
    });

    await user.selectOptions(
      within(rigaDi("Slack #ops")).getByRole("combobox"),
      "Non collegato",
    );

    await waitFor(() => expect(chiamato).toBe("DELETE"));
  });

  it("un errore dell'API resta visibile invece di far sparire la modifica", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`/api/v1/groups/${GROUP_ID}/channels`, () =>
        HttpResponse.json(
          {
            type: "/problems/not-found",
            title: "Not Found",
            status: 404,
            detail: "Channel not found.",
          },
          { status: 404 },
        ),
      ),
    );

    renderBindings();
    await waitFor(() => expect(screen.getByText(/Slack #ops/)).toBeInTheDocument());

    await user.selectOptions(within(rigaDi("Slack #ops")).getByRole("combobox"), "error");

    expect(await screen.findByText(/Channel not found/)).toBeInTheDocument();
  });
});
