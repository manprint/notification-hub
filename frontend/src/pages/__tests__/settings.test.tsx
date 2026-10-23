import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import SettingsPage from "../SettingsPage";
import { setRefreshToken } from "../../api/client";
import { fixtureMe, fixtureTenant } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

describe("SettingsPage", () => {
  it("T-UI18 test_conflitto_cap_elenca_i_receiver: un 409 con conflicting_receivers mostra i nomi", async () => {
    server.use(
      http.patch("/api/v1/tenant", () =>
        HttpResponse.json(
          {
            type: "/problems/conflict",
            title: "Conflict",
            status: 409,
            detail: "Some receivers have a higher max_body_bytes than requested.",
            conflicting_receivers: [
              {
                id: "r-1",
                name: "Backup notturno",
                group_name: "Produzione",
                max_body_bytes: 5_000_000,
              },
              { id: "r-2", name: "API pubblica", group_name: "Web", max_body_bytes: 2_000_000 },
            ],
          },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/cap corpo/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/cap corpo/i), "500000");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => {
      expect(screen.getByText(/Backup notturno/)).toBeInTheDocument();
    });
    expect(screen.getByText(/API pubblica/)).toBeInTheDocument();
  });

  it("un admin vede le schede dell'audit ma non il modulo delle quote", async () => {
    // La sessione si carica solo con un refresh token presente: senza, il
    // ruolo resta null e la pagina non saprebbe di avere davanti un admin.
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.get("/api/v1/auth/me", () => HttpResponse.json({ ...fixtureMe, role: "admin" })),
    );

    renderWithProviders(<SettingsPage />);

    expect(
      await screen.findByText(/Le impostazioni generali sono riservate all'owner/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Audit" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Letture e verifiche" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Generali" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/cap corpo/i)).not.toBeInTheDocument();
  });

  it("l'owner puo' impostare la retention dell'audit", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch("/api/v1/tenant", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({});
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/retention audit/i)).toBeInTheDocument();
    });
    await user.type(screen.getByLabelText(/retention audit/i), "730");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => {
      expect(bodies).toEqual([{ audit_retention_days: 730 }]);
    });
  });

  function catturaPatch() {
    const bodies: unknown[] = [];
    server.use(
      http.patch("/api/v1/tenant", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(fixtureTenant);
      }),
    );
    return bodies;
  }

  it("la spunta «senza scadenza» manda null esplicito: si torna a illimitata", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    // retention_days è 90 nella fixture: la spunta parte tolta.
    const spunta = await screen.findByRole("checkbox", { name: "Notifiche senza scadenza" });
    expect(spunta).not.toBeChecked();
    await user.click(spunta);
    expect(screen.getByLabelText("Retention (giorni)")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Prima un campo vuoto veniva omesso e non c'era modo di togliere un limite.
    await waitFor(() => expect(bodies).toEqual([{ retention_days: null }]));
  });

  it("una quota già illimitata si presenta spuntata e si può limitare", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    const spunta = await screen.findByRole("checkbox", { name: "Nessuna quota giornaliera" });
    expect(spunta).toBeChecked();
    await user.click(spunta);
    await user.type(screen.getByLabelText("Quota giornaliera notifiche"), "5000");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(bodies).toEqual([{ max_notifications_per_day: 5000 }]));
  });

  it("togliere la spunta senza indicare un limite non manda niente e lo dice sul campo", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", { name: "Nessuna quota giornaliera" }));
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(await screen.findByText(/Indica un limite, o rimetti la spunta/)).toBeInTheDocument();
    expect(screen.getByLabelText("Quota giornaliera notifiche")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(bodies).toEqual([]);
  });

  it("lo spazio massimo si imposta dal modulo", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", { name: "Spazio illimitato" }));
    await user.type(screen.getByLabelText("Spazio massimo (byte)"), "1073741824");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(bodies).toEqual([{ max_storage_bytes: 1073741824 }]));
    // E compare fra i valori in vigore, anche quando è illimitato.
    const inVigore = screen.getByRole("heading", { name: "Valori in vigore" }).closest(".card");
    expect(within(inVigore as HTMLElement).getByText("Spazio massimo")).toBeInTheDocument();
  });

  it("il cap corpo oltre 20 MiB viene fermato prima della richiesta", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    const campo = await screen.findByLabelText(/cap corpo/i);
    expect(campo).toHaveAttribute("max", "20971520");
    await user.type(campo, "20971521");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    expect(await screen.findByText(/non può superare/)).toBeInTheDocument();
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(bodies).toEqual([]);

    await user.clear(campo);
    await user.type(campo, "20971520");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(bodies).toEqual([{ max_body_bytes: 20971520 }]));
  });

  it("se il caricamento del tenant fallisce la pagina resta con titolo, schede e messaggio", async () => {
    server.use(
      http.get("/api/v1/tenant", () =>
        HttpResponse.json(
          { type: "/problems/internal", title: "Internal Server Error", status: 500 },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<SettingsPage />);

    // Prima la pagina diventava vuota: nessun titolo, nessuna scheda, nessuna spiegazione.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Impostazioni" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Audit" })).toBeInTheDocument();
  });

  it("una quota oltre il massimo dello schema si ferma sul campo, senza richiesta", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    const retention = await screen.findByLabelText("Retention (giorni)");
    expect(retention).toHaveAttribute("max", "2147483647");
    await user.type(retention, "3000000000");
    // Lo spazio parte illimitato nella fixture: si toglie la spunta per scriverci.
    await user.click(screen.getByRole("checkbox", { name: "Spazio illimitato" }));
    const spazio = screen.getByLabelText("Spazio massimo (byte)");
    await user.type(spazio, "99999999999999999999");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Prima il server rispondeva 422 in inglese, o 500 oltre il bigint.
    expect(await screen.findByText("Il massimo è 2147483647.")).toBeInTheDocument();
    expect(screen.getByText("Il massimo è 9007199254740991.")).toBeInTheDocument();
    expect(retention).toHaveAttribute("aria-invalid", "true");
    expect(bodies).toEqual([]);
  });

  it("il valore appena sopra il bigint viene fermato prima della richiesta", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", { name: "Spazio illimitato" }));
    const spazio = screen.getByLabelText("Spazio massimo (byte)");
    await user.type(spazio, "9223372036854775808");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    expect(await screen.findByText("Il massimo è 9007199254740991.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("lo spazio al tetto esatto parte con le cifre intere, senza arrotondarle", async () => {
    // Il JSON di un numero JS arrotonda oltre 2^53: 9223372036854775807 partiva
    // come 9223372036854776000 e il backend lo rifiutava con 422. Qui il massimo
    // è 2^53-1, che si legge esatto: il corpo grezzo deve contenere quelle cifre.
    const raw: string[] = [];
    server.use(
      http.patch("/api/v1/tenant", async ({ request }) => {
        raw.push(await request.text());
        return HttpResponse.json(fixtureTenant);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", { name: "Spazio illimitato" }));
    const spazio = screen.getByLabelText("Spazio massimo (byte)");
    await user.type(spazio, "9007199254740991");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(raw).toHaveLength(1));
    expect(raw[0]).toBe('{"max_storage_bytes":9007199254740991}');
  });

  it("il valore 9223372036854775807 si ferma sul campo invece di partire arrotondato", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", { name: "Spazio illimitato" }));
    await user.type(screen.getByLabelText("Spazio massimo (byte)"), "9223372036854775807");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    expect(await screen.findByText("Il massimo è 9007199254740991.")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("gli zeri in testa non contano fra le cifre: 0…01 vale 1", async () => {
    const bodies = catturaPatch();
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.click(await screen.findByRole("checkbox", { name: "Spazio illimitato" }));
    await user.type(screen.getByLabelText("Spazio massimo (byte)"), "00000000000000000000001");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(bodies).toEqual([{ max_storage_bytes: 1 }]));
  });

  it("a salvataggio riuscito si svuota ciò che è partito, non ciò che si è digitato dopo", async () => {
    let rilascia: () => void = () => {};
    const attesa = new Promise<void>((resolve) => {
      rilascia = resolve;
    });
    server.use(
      http.patch("/api/v1/tenant", async () => {
        await attesa;
        return HttpResponse.json(fixtureTenant);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    const cap = await screen.findByLabelText(/cap corpo/i);
    await user.type(cap, "5000");
    await user.click(screen.getByRole("button", { name: "Salva" }));
    // Mentre la richiesta è in volo chi scrive continua a digitare.
    const retention = screen.getByLabelText("Retention (giorni)");
    await user.type(retention, "6");
    rilascia();

    await waitFor(() => expect(cap).toHaveValue(null));
    expect(retention).toHaveValue(6);
  });

  it("l'elenco dei receiver in conflitto mostra due voci anche con lo stesso nome", async () => {
    server.use(
      http.patch("/api/v1/tenant", () =>
        HttpResponse.json(
          {
            type: "/problems/conflict",
            title: "Conflict",
            status: 409,
            detail: "Some receivers have a higher max_body_bytes than requested.",
            conflicting_receivers: [
              {
                id: "r-1",
                name: "backup",
                group_name: "Produzione",
                max_body_bytes: 5_000_000,
              },
              { id: "r-2", name: "backup", group_name: "Staging", max_body_bytes: 6_000_000 },
            ],
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />);

    await user.type(await screen.findByLabelText(/cap corpo/i), "500000");
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Nomi uguali in gruppi diversi: due righe, ciascuna con il suo gruppo e il suo valore.
    expect(await screen.findAllByText(/^backup \(gruppo /)).toHaveLength(2);
    expect(screen.getByText(/^backup \(gruppo Produzione\)/)).toBeInTheDocument();
    expect(screen.getByText(/^backup \(gruppo Staging\)/)).toBeInTheDocument();
  });
});
