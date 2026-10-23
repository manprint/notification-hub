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
});
