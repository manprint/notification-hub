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
              { name: "Backup notturno", max_body_bytes: 5_000_000 },
              { name: "API pubblica", max_body_bytes: 2_000_000 },
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
});
