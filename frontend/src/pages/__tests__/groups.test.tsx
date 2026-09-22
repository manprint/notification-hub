import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import GroupsPage from "../GroupsPage";
import { setRefreshToken } from "../../api/client";
import { fixtureDeleteImpact, fixtureGroups } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

describe("GroupsPage", () => {
  it("T-UI12 test_cancellazione_gruppo_mostra_impatto: mostra i conteggi e richiede il nome esatto", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByRole("button", { name: "Elimina gruppo" });
    await user.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getByText(`${fixtureDeleteImpact.receivers} receiver`)).toBeInTheDocument();
    });
    expect(screen.getByText(`${fixtureDeleteImpact.notifications} notifiche`)).toBeInTheDocument();
    expect(screen.getByText(`${fixtureDeleteImpact.deliveries} consegne`)).toBeInTheDocument();

    // L'etichetta dice cosa succede, non "Conferma": è l'ultimo punto in cui
    // si può capire che si sta cancellando un gruppo intero. Va cercata dentro
    // il dialogo, perché il pulsante della riga si chiama allo stesso modo.
    const dialogo = within(screen.getByRole("dialog"));
    const confirmButton = dialogo.getByRole("button", { name: "Elimina gruppo" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByLabelText(/digita/i), "Server Produzione");
    expect(confirmButton).toBeEnabled();
  });

  it("T-GRP2 test_groups_tabella_ricerca_e_apri: la tabella mostra conteggio e la ricerca filtra", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });

    expect(screen.getAllByRole("button", { name: "Apri" })).toHaveLength(2);

    const g1Row = screen.getByRole("row", { name: /server produzione/i });
    expect(within(g1Row).getByText("1")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Cerca gruppi"), "backup");
    expect(screen.queryByText("Server Produzione")).toBeNull();
    expect(screen.getByRole("row", { name: /backup/i })).toBeInTheDocument();
  });

  it("svuotare la descrizione la toglie davvero e la riga la mostra vuota", async () => {
    setRefreshToken("refresh-token-fixture");
    let groups = fixtureGroups.map((g) => ({ ...g }));
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get("/api/v1/groups", () => HttpResponse.json(groups)),
      http.patch("/api/v1/groups/:groupId", async ({ request, params }) => {
        body = (await request.json()) as Record<string, unknown>;
        // Il contratto del backend: "" (o null) esplicito svuota.
        const description = body.description ? String(body.description) : null;
        groups = groups.map((g) => (g.id === params.groupId ? { ...g, description } : g));
        return HttpResponse.json(groups.find((g) => g.id === params.groupId));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await screen.findByText("Ambiente di produzione");
    const riga = screen.getByRole("row", { name: /server produzione/i });
    await user.click(within(riga).getByRole("button", { name: "Modifica gruppo" }));
    const dialogo = within(screen.getByRole("dialog"));
    await user.clear(dialogo.getByLabelText("Descrizione"));
    await user.click(dialogo.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ name: "Server Produzione", description: "" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() =>
      expect(screen.queryByText("Ambiente di produzione")).not.toBeInTheDocument(),
    );
  });

  it("un doppio click sulla conferma di eliminazione manda una sola DELETE", async () => {
    setRefreshToken("refresh-token-fixture");
    let deletes = 0;
    server.use(
      http.delete("/api/v1/groups/:groupId", async () => {
        deletes += 1;
        await new Promise((resolve) => setTimeout(resolve, 30));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await screen.findByText("Server Produzione");
    await user.click(screen.getAllByRole("button", { name: "Elimina gruppo" })[0]);
    const dialogo = within(await screen.findByRole("dialog"));
    await user.type(dialogo.getByLabelText(/digita/i), "Server Produzione");
    await user.dblClick(dialogo.getByRole("button", { name: "Elimina gruppo" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deletes).toBe(1);
  });
});
