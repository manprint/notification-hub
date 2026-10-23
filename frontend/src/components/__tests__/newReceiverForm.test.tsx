import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import NewReceiverForm from "../NewReceiverForm";
import { fixtureReceiver } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "../../pages/__tests__/testUtils";

describe("NewReceiverForm", () => {
  it("la severity di default si sceglie con le etichette italiane, il valore resta quello dell'API", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewReceiverForm groupId="g1" />);
    await user.click(screen.getByText("Nuovo receiver"));

    const tendina = screen.getByLabelText("Severity di default");
    expect(within(tendina).getByRole("option", { name: "Critica" })).toHaveAttribute(
      "value",
      "critical",
    );
    expect(within(tendina).queryByRole("option", { name: "critical" })).toBeNull();
  });

  it("T-NRF1 il receiver creato compare in tutti gli elenchi, non solo nel gruppo", async () => {
    const user = userEvent.setup();
    const invalida = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/groups/g1/receivers", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureReceiver, id: "r9", name: "Rsync" }, { status: 201 });
      }),
    );

    try {
      renderWithProviders(<NewReceiverForm groupId="g1" />);
      await user.click(screen.getByText("Nuovo receiver"));
      await user.type(screen.getByLabelText(/Nome receiver/), "  Rsync ");
      await user.click(screen.getByRole("button", { name: "Aggiungi receiver" }));

      await waitFor(() => expect(inviato).toEqual({ name: "Rsync", default_severity: "info" }));
      // Selettore receiver delle notifiche, override dei canali e conteggio del
      // gruppo leggono chiavi diverse dalla tabella del gruppo.
      await waitFor(() => {
        const chiavi = invalida.mock.calls.map(([filtro]) => JSON.stringify(filtro?.queryKey));
        expect(chiavi).toEqual(
          expect.arrayContaining([
            JSON.stringify(["receivers", "g1"]),
            JSON.stringify(["group-receivers", "g1"]),
            JSON.stringify(["receivers-all"]),
            JSON.stringify(["group", "g1"]),
            JSON.stringify(["groups"]),
          ]),
        );
      });
    } finally {
      invalida.mockRestore();
    }
  });

  it("un nome vuoto mostra il messaggio sul campo, non il fumetto del browser, e non crea nulla", async () => {
    const user = userEvent.setup();
    let creati = 0;
    server.use(
      http.post("/api/v1/groups/g1/receivers", () => {
        creati += 1;
        return HttpResponse.json(fixtureReceiver, { status: 201 });
      }),
    );
    renderWithProviders(<NewReceiverForm groupId="g1" />);
    await user.click(screen.getByText("Nuovo receiver"));
    await user.click(screen.getByRole("button", { name: "Aggiungi receiver" }));

    expect(await screen.findByText("Il nome del receiver è obbligatorio.")).toBeInTheDocument();
    expect(creati).toBe(0);
  });

  it("la severity di default è obbligatoria, come nel modulo di modifica", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NewReceiverForm groupId="g1" />);
    await user.click(screen.getByText("Nuovo receiver"));

    expect(screen.getByLabelText("Severity di default")).toBeRequired();
  });
});
