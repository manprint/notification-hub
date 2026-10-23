import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import UsersPage from "../UsersPage";
import { getRefreshToken, setAccessToken, setRefreshToken } from "../../api/client";
import { fixtureMe, fixtureTokenPair, fixtureUsers } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

const OWNER_ID = fixtureUsers[0].id;
const MEMBER_ID = fixtureUsers[1].id;

function aspetta(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Sessione caricata come l'owner della fixture (la prima riga della tabella). */
async function renderComeOwner() {
  setRefreshToken("refresh-token-fixture");
  renderWithProviders(<UsersPage />);
  const riga = await screen.findByRole("row", { name: /owner@acme\.test/ });
  await within(riga).findByText("(tu)");
  return riga;
}

describe("UsersPage", () => {
  beforeEach(() => {
    setAccessToken(null);
    localStorage.clear();
  });

  it("T-UI19 test_link_invito_sempre_copiabile: con email_sent false il link resta copiabile", async () => {
    server.use(
      http.post("/api/v1/invitations", () =>
        HttpResponse.json(
          {
            id: "inv1",
            email: "nuovo@acme.test",
            role: "member",
            expires_at: "2026-08-08T00:00:00Z",
            invite_url: "https://notifyhub.example.com/invite#token=abc123",
            email_sent: false,
          },
          { status: 201 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    await waitFor(() => {
      expect(screen.getByText("owner@acme.test")).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText("email@esempio.it"), "nuovo@acme.test");
    await user.click(screen.getByRole("button", { name: "Invita" }));

    await waitFor(() => {
      expect(screen.getByText(/Email non inviata/)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /copia link/i })).toBeInTheDocument();
  });

  it("T-UI24 test_form_utenza_etichettato: i campi hanno etichetta e non stanno piu' in riga", async () => {
    renderWithProviders(<UsersPage />);

    await waitFor(() => {
      expect(screen.getByText("owner@acme.test")).toBeInTheDocument();
    });

    // Etichette associate: un campo largo senza <label> non sarebbe navigabile
    // da tastiera ne' leggibile da uno screen reader.
    const email = screen.getByLabelText("Email", { selector: "#create-user-email" });
    const password = screen.getByLabelText("Password", { selector: "#create-user-password" });
    expect(email).toHaveAttribute("type", "email");
    expect(password).toHaveAttribute("minlength", "12");
    expect(screen.getByLabelText("Ruolo", { selector: "#create-user-role" })).toBeInTheDocument();
    expect(screen.getByText("Almeno 12 caratteri.")).toBeInTheDocument();

    // I campi stanno in un form impilato, non nella riga flex .toolbar che li
    // comprimeva alla larghezza di default del browser.
    const form = email.closest("form");
    expect(form).toHaveClass("form-stacked");
    expect(form?.querySelector(".toolbar")).toBeNull();
  });

  it("T-UI25 test_creazione_utenza_invia_i_campi: il form impilato manda email, password, ruolo e gruppi", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/users", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: "u9" }, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    await waitFor(() => {
      expect(screen.getByText("owner@acme.test")).toBeInTheDocument();
    });

    await user.type(
      screen.getByLabelText("Email", { selector: "#create-user-email" }),
      "nuova@acme.test",
    );
    await user.type(
      screen.getByLabelText("Password", { selector: "#create-user-password" }),
      "password-lunghissima",
    );
    await user.selectOptions(
      screen.getByLabelText("Ruolo", { selector: "#create-user-role" }),
      "admin",
    );
    await user.click(screen.getByRole("button", { name: "Crea" }));

    await waitFor(() => {
      expect(body).not.toBeNull();
    });
    expect(body).toMatchObject({
      email: "nuova@acme.test",
      password: "password-lunghissima",
      role: "admin",
    });
  });

  it("dopo una modifica le righe restano nell'ordine per email che manda l'API", async () => {
    // L'API ordina per email: la tabella mostra quell'ordine, anche dopo che una
    // riga è cambiata e l'elenco è stato riletto.
    const [owner, member] = fixtureUsers;
    let ruoloMember = member.role;
    server.use(
      http.get("/api/v1/users", () =>
        HttpResponse.json([
          { ...member, id: "44444444-4444-4444-4444-444444444444", email: "admin@acme.test", role: "admin" },
          { ...member, role: ruoloMember },
          owner,
          { ...member, id: "55555555-5555-5555-5555-555555555555", email: "viewer@acme.test", role: "viewer" },
        ]),
      ),
      http.patch("/api/v1/users/:id", async ({ request }) => {
        ruoloMember = ((await request.json()) as { role: string }).role;
        return HttpResponse.json({});
      }),
    );
    const emailNelleRighe = () =>
      screen
        .getAllByRole("row")
        .map((riga) => riga.textContent?.match(/[\w.]+@acme\.test/)?.[0])
        .filter(Boolean);
    const ordine = ["admin@acme.test", "member@acme.test", "owner@acme.test", "viewer@acme.test"];
    const user = userEvent.setup();
    await renderComeOwner();
    expect(emailNelleRighe()).toEqual(ordine);

    await user.selectOptions(screen.getByLabelText("Ruolo di member@acme.test"), "viewer");
    await waitFor(() => expect(ruoloMember).toBe("viewer"));
    await waitFor(() =>
      expect(screen.getByLabelText("Ruolo di member@acme.test")).toHaveValue("viewer"),
    );
    expect(emailNelleRighe()).toEqual(ordine);
  });

  it("il proprio ruolo si cambia solo dopo una conferma, e poi la sessione si ricarica", async () => {
    const patches: unknown[] = [];
    let meCalls = 0;
    let refreshCalls = 0;
    server.use(
      http.get("/api/v1/auth/me", () => {
        meCalls += 1;
        return HttpResponse.json(fixtureMe);
      }),
      http.post("/api/v1/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json(fixtureTokenPair);
      }),
      http.patch("/api/v1/users/:id", async ({ request }) => {
        patches.push(await request.json());
        return HttpResponse.json({});
      }),
    );
    const user = userEvent.setup();
    const riga = await renderComeOwner();
    const tendina = within(riga).getByLabelText("Ruolo di owner@acme.test");

    // Annullare lascia tutto com'era.
    await user.selectOptions(tendina, "member");
    await user.click(
      within(await screen.findByRole("dialog", { name: "Cambia il tuo ruolo" })).getByRole(
        "button",
        { name: "Annulla" },
      ),
    );
    expect(patches).toEqual([]);
    expect(tendina).toHaveValue("owner");

    const meBefore = meCalls;
    const refreshBefore = refreshCalls;
    await user.selectOptions(tendina, "admin");
    const dialogo = await screen.findByRole("dialog", { name: "Cambia il tuo ruolo" });
    expect(patches).toEqual([]);
    await user.click(within(dialogo).getByRole("button", { name: "Diventa Amministratore" }));

    await waitFor(() => expect(patches).toEqual([{ role: "admin" }]));
    // Ruolo della sessione riletto (e token ruotati, perché il backend autorizza
    // col ruolo scritto nel token): senza, la UI restava quella dell'owner.
    await waitFor(() => expect(meCalls).toBe(meBefore + 1));
    expect(refreshCalls).toBe(refreshBefore + 1);
  });

  it("rimuovere se stessi chiede conferma, poi chiude la sessione", async () => {
    const deleted: unknown[] = [];
    let logoutBody: unknown = null;
    server.use(
      http.delete("/api/v1/users/:id", ({ params }) => {
        deleted.push(params.id);
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("/api/v1/auth/logout", async ({ request }) => {
        logoutBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    const riga = await renderComeOwner();

    await user.click(within(riga).getByRole("button", { name: "Rimuovi" }));
    const dialogo = await screen.findByRole("dialog", { name: "Rimuovi la tua utenza" });
    expect(deleted).toEqual([]);
    await user.click(within(dialogo).getByRole("button", { name: "Rimuovi la mia utenza" }));

    await waitFor(() => expect(deleted).toEqual([OWNER_ID]));
    await waitFor(() => expect(getRefreshToken()).toBeNull());
    expect(logoutBody).toEqual({ refresh_token: expect.any(String) });
  });

  it("un admin non può toccare le righe degli owner né concedere il ruolo owner", async () => {
    let meServed = false;
    server.use(
      http.get("/api/v1/auth/me", () => {
        meServed = true;
        return HttpResponse.json({
          ...fixtureMe,
          id: "44444444-4444-4444-4444-444444444444",
          email: "admin@acme.test",
          role: "admin",
        });
      }),
    );
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<UsersPage />);
    const rigaOwner = await screen.findByRole("row", { name: /owner@acme\.test/ });
    await waitFor(() => expect(meServed).toBe(true));

    // Il backend risponde 403: offrire l'azione voleva dire un errore certo.
    await waitFor(() =>
      expect(within(rigaOwner).getByLabelText("Ruolo di owner@acme.test")).toBeDisabled(),
    );
    expect(within(rigaOwner).getByRole("button", { name: "Rimuovi" })).toBeDisabled();
    for (const casella of within(rigaOwner).getAllByRole("checkbox")) {
      expect(casella).toBeDisabled();
    }

    const rigaMember = screen.getByRole("row", { name: /member@acme\.test/ });
    const tendinaMember = within(rigaMember).getByLabelText("Ruolo di member@acme.test");
    expect(tendinaMember).toBeEnabled();
    expect(within(tendinaMember).queryByRole("option", { name: "Proprietario" })).toBeNull();
    for (const selector of ["#invite-role", "#create-user-role"]) {
      const tendina = screen.getByLabelText("Ruolo", { selector });
      expect(within(tendina).queryByRole("option", { name: "Proprietario" })).toBeNull();
      expect(within(tendina).getByRole("option", { name: "Amministratore" })).toBeInTheDocument();
    }
  });

  it("l'owner può concedere il ruolo owner", async () => {
    await renderComeOwner();
    for (const selector of ["#invite-role", "#create-user-role"]) {
      const tendina = screen.getByLabelText("Ruolo", { selector });
      expect(within(tendina).getByRole("option", { name: "Proprietario" })).toBeInTheDocument();
    }
  });

  it("click ravvicinati sui gruppi non perdono aggiornamenti", async () => {
    let users: Array<Omit<(typeof fixtureUsers)[number], "group_ids"> & { group_ids: string[] }> =
      fixtureUsers.map((u) => ({ ...u, group_ids: [...u.group_ids] }));
    const patches: unknown[] = [];
    server.use(
      http.get("/api/v1/users", () => HttpResponse.json(users)),
      http.patch("/api/v1/users/:id", async ({ request, params }) => {
        const body = (await request.json()) as { group_ids: string[] };
        patches.push(body);
        await aspetta(40);
        users = users.map((u) => (u.id === params.id ? { ...u, group_ids: body.group_ids } : u));
        return HttpResponse.json(users.find((u) => u.id === params.id));
      }),
    );
    const user = userEvent.setup();
    await renderComeOwner();
    const riga = screen.getByRole("row", { name: /member@acme\.test/ });
    await user.click(within(riga).getByText("Nessuno"));

    const produzione = within(riga).getByRole("checkbox", { name: "Server Produzione" });
    const backup = within(riga).getByRole("checkbox", { name: "Backup" });
    await user.click(produzione);
    // Il secondo click partiva dalla lista in cache (ancora vuota) e il suo
    // salvataggio cancellava il primo. Il click su un controllo disabilitato è
    // sincrono: user.click lo rimanderebbe a salvataggio finito, quando il
    // controllo è di nuovo attivo, e il test salverebbe due volte.
    expect(backup).toBeDisabled();
    fireEvent.click(backup);
    expect(patches).toHaveLength(1);

    await waitFor(() => expect(backup).toBeEnabled());
    await user.click(backup);

    await waitFor(() =>
      expect(users.find((u) => u.id === MEMBER_ID)?.group_ids).toEqual(["g1", "g2"]),
    );
    expect(patches).toEqual([{ group_ids: ["g1"] }, { group_ids: ["g1", "g2"] }]);
  });

  it("un doppio click sulla conferma di rimozione manda una sola DELETE", async () => {
    let deletes = 0;
    server.use(
      http.delete("/api/v1/users/:id", async () => {
        deletes += 1;
        await aspetta(30);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    await renderComeOwner();
    const riga = screen.getByRole("row", { name: /member@acme\.test/ });

    await user.click(within(riga).getByRole("button", { name: "Rimuovi" }));
    const dialogo = await screen.findByRole("dialog", { name: "Rimuovi member@acme.test" });
    await user.dblClick(within(dialogo).getByRole("button", { name: "Rimuovi utenza" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deletes).toBe(1);
  });

  it("un doppio click sulla revoca di un invito manda una sola DELETE", async () => {
    let deletes = 0;
    server.use(
      http.get("/api/v1/invitations", () =>
        HttpResponse.json([
          {
            id: "inv1",
            email: "invitato@acme.test",
            role: "member",
            expires_at: "2026-10-01T00:00:00Z",
            accepted_at: null,
          },
        ]),
      ),
      http.delete("/api/v1/invitations/:id", async () => {
        deletes += 1;
        await aspetta(30);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    await user.click(await screen.findByRole("button", { name: "Revoca" }));
    const dialogo = await screen.findByRole("dialog");
    await user.dblClick(within(dialogo).getByRole("button", { name: "Revoca invito" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deletes).toBe(1);
  });

  it("la password dell'utenza si conta in caratteri, come fa il backend", async () => {
    let posts = 0;
    server.use(
      http.post("/api/v1/users", () => {
        posts += 1;
        return HttpResponse.json({ id: "u9" }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);
    await screen.findByText("owner@acme.test");

    await user.type(
      screen.getByLabelText("Email", { selector: "#create-user-email" }),
      "nuova@acme.test",
    );
    // Undici caratteri ma dodici unità UTF-16.
    await user.type(
      screen.getByLabelText("Password", { selector: "#create-user-password" }),
      "abcdefghij\u{1F600}",
    );
    await user.click(screen.getByRole("button", { name: "Crea" }));

    expect(await screen.findByText(/almeno 12 caratteri\./)).toBeInTheDocument();
    expect(posts).toBe(0);
  });

  it("gli inviti che non si caricano mostrano l'errore nella loro card, non la fanno sparire", async () => {
    server.use(
      http.get("/api/v1/invitations", () =>
        HttpResponse.json(
          {
            type: "/problems/internal",
            title: "Internal Server Error",
            status: 500,
            detail: "Inviti non disponibili",
          },
          { status: 500, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    renderWithProviders(<UsersPage />);

    const titolo = await screen.findByRole("heading", { name: "Inviti in sospeso" });
    const card = titolo.closest(".card") as HTMLElement;
    expect(await within(card).findByRole("alert")).toHaveTextContent("Inviti non disponibili");
    // Nessuna tabella vuota sotto l'errore: il messaggio è l'unico contenuto.
    expect(within(card).queryByRole("table")).not.toBeInTheDocument();
  });

  it("senza inviti e senza errore la card degli inviti non compare", async () => {
    renderWithProviders(<UsersPage />);

    await screen.findByRole("heading", { name: "Utenze" });
    expect(screen.queryByRole("heading", { name: "Inviti in sospeso" })).not.toBeInTheDocument();
  });

  it("le caselle dei gruppi nel modulo di creazione hanno la domanda come nome del gruppo", async () => {
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.get("/api/v1/groups", () =>
        HttpResponse.json([
          { id: "g1", name: "Server Produzione", description: null, receiver_count: 0, notification_count: 0, unread_count: 0 },
        ]),
      ),
    );
    renderWithProviders(<UsersPage />);

    const gruppo = await screen.findByRole("group", { name: /Gruppi di receiver da gestire/ });
    expect(within(gruppo).getByRole("checkbox", { name: "Server Produzione" })).toBeInTheDocument();
  });

  it("il campo password del modulo di creazione non ripete l'etichetta come segnaposto", async () => {
    renderWithProviders(<UsersPage />);

    const campo = await screen.findByLabelText("Password", { selector: "#create-user-password" });
    expect(campo).not.toHaveAttribute("placeholder");
  });

  it("la password di 8 caratteri nel modulo di creazione mostra il messaggio italiano", async () => {
    setRefreshToken("refresh-token-fixture");
    let creazioni = 0;
    server.use(
      http.post("/api/v1/users", () => {
        creazioni += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    await user.type(
      await screen.findByLabelText("Email", { selector: "#create-user-email" }),
      "nuova@acme.test",
    );
    await user.type(screen.getByLabelText("Password", { selector: "#create-user-password" }), "12345678");
    await user.click(screen.getByRole("button", { name: "Crea" }));

    // Il vincolo minLength nativo fermava l'invio col fumetto del browser.
    expect(await screen.findByText("La password deve avere almeno 12 caratteri.")).toBeInTheDocument();
    expect(creazioni).toBe(0);
  });

  it("l'invito inviato svuota l'email solo se non è stata riscritta nel frattempo", async () => {
    let rilascia: () => void = () => {};
    const attesa = new Promise<void>((resolve) => {
      rilascia = resolve;
    });
    server.use(
      http.post("/api/v1/invitations", async () => {
        await attesa;
        return HttpResponse.json(
          {
            id: "inv1",
            email: "primo@acme.test",
            role: "member",
            expires_at: "2026-08-08T00:00:00Z",
            invite_url: "https://notifyhub.example.com/invite#token=abc123",
            email_sent: true,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    const email = await screen.findByPlaceholderText("email@esempio.it");
    await user.type(email, "primo@acme.test");
    await user.click(screen.getByRole("button", { name: "Invita" }));
    await user.type(email, "x");
    rilascia();

    await waitFor(() => expect(screen.getByRole("button", { name: "Invita" })).toBeEnabled());
    // Il campo non si svuota: la digitazione durante l'invio è ancora lì.
    expect(email).toHaveValue("primo@acme.testx");
  });

  it("le righe degli owner in sola lettura dicono il motivo anche a schermo", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          ...fixtureMe,
          id: "44444444-4444-4444-4444-444444444444",
          email: "admin@acme.test",
          role: "admin",
        }),
      ),
    );
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<UsersPage />);

    const rigaOwner = await screen.findByRole("row", { name: /owner@acme\.test/ });
    const motivo = "Solo un owner può modificare o rimuovere un altro owner.";
    expect(within(rigaOwner).getByText(motivo)).toBeInTheDocument();
    expect(within(rigaOwner).getByLabelText("Ruolo di owner@acme.test")).toHaveAccessibleDescription(
      motivo,
    );
  });

  it("le colonne delle azioni hanno un nome, anche se visivamente non c'è scritto", async () => {
    renderWithProviders(<UsersPage />);

    const utenze = (await screen.findByRole("heading", { name: "Utenze" })).closest(".card") as HTMLElement;
    const tabella = await within(utenze).findByRole("table");
    const intestazioni = within(tabella).getAllByRole("columnheader");
    expect(intestazioni[intestazioni.length - 1]).toHaveAccessibleName("Azioni");
  });
});
