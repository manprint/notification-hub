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

    expect(screen.getAllByRole("link", { name: "Apri" })).toHaveLength(2);

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

  it.each(["member", "viewer"])(
    "T-ROLE1 con ruolo %s la pagina Gruppi non offre la gestione, come l'API",
    async (ruolo) => {
      server.use(
        http.get("/api/v1/auth/me", () =>
          HttpResponse.json({
            id: "u2",
            email: `${ruolo}@acme.test`,
            role: ruolo,
            tenant_id: "t1",
            tenant_name: "ACME",
          }),
        ),
      );
      setRefreshToken("refresh-token-fixture");
      renderWithProviders(<GroupsPage />);

      await waitFor(() => {
        expect(screen.getByText("Server Produzione")).toBeInTheDocument();
      });
      expect(screen.queryByText("Nuovo gruppo")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Modifica gruppo" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Elimina gruppo" })).not.toBeInTheDocument();
      // Aprire il gruppo resta permesso a tutti.
      expect(screen.getAllByRole("link", { name: "Apri" })).toHaveLength(2);
    },
  );

  it("T-DEL3 il motivo del rifiuto di una cancellazione resta nel dialogo aperto", async () => {
    server.use(
      http.delete("/api/v1/groups/:groupId", () =>
        HttpResponse.json(
          {
            type: "/problems/unprocessable",
            title: "Unprocessable",
            status: 422,
            detail: "confirm must match the exact group name.",
          },
          { status: 422 },
        ),
      ),
    );
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });
    await user.click(screen.getAllByRole("button", { name: "Elimina gruppo" })[0]);
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Digita/), "Server Produzione");
    await user.click(within(dialog).getByRole("button", { name: "Elimina gruppo" }));

    // Il toast scompare dopo pochi secondi: il dialogo deve dire perché è rimasto aperto.
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("T-DEL4 un errore nel caricare l'impatto non spinge fuori la colonna delle azioni", async () => {
    server.use(
      http.get("/api/v1/groups/:groupId/delete-impact", () =>
        HttpResponse.json(
          { type: "/problems/internal", title: "Internal", status: 500, detail: "Boom." },
          { status: 500 },
        ),
      ),
    );
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });
    await user.click(screen.getAllByRole("button", { name: "Elimina gruppo" })[0]);

    const avviso = await screen.findByRole("alert");
    expect(avviso).toBeInTheDocument();
    expect(avviso.closest(".row-actions")).toBeNull();
  });

  it("T-GRP5 la creazione manda anche la descrizione del gruppo", async () => {
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/groups", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fixtureGroups[0], ...inviato }, { status: 201 });
      }),
    );
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });
    await user.type(screen.getByLabelText("Nome"), "Backup notturni");
    await user.type(screen.getByLabelText("Descrizione"), "Job di notte");
    await user.click(screen.getByRole("button", { name: "Crea gruppo" }));

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).toEqual({ name: "Backup notturni", description: "Job di notte" });
  });

  it("T-GRP6 la finestra di modifica non si chiude con Esc mentre il salvataggio è in corso", async () => {
    let rispondi: () => void = () => undefined;
    server.use(
      http.patch("/api/v1/groups/:groupId", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json(fixtureGroups[0]);
      }),
    );
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });
    await user.click(screen.getAllByRole("button", { name: "Modifica gruppo" })[0]);
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await user.keyboard("{Escape}");

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    rispondi();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("T-GRP7 la tabella dei gruppi sta dentro una card e il nome accetta 255 caratteri", async () => {
    setRefreshToken("refresh-token-fixture");
    const { container } = renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });
    expect(container.querySelector(".table-wrap")?.closest(".card")).not.toBeNull();
    expect(screen.getByLabelText("Nome")).toHaveAttribute("maxlength", "255");
  });

  it("il nome del gruppo nella tabella è un collegamento al dettaglio, oltre al pulsante Apri", async () => {
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<GroupsPage />);

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Server Produzione" })).toHaveAttribute(
      "href",
      `/groups/${fixtureGroups[0].id}`,
    );
  });
});
