import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import SettingsPage from "../SettingsPage";
import { setRefreshToken } from "../../api/client";
import { fixtureMe } from "../../api/mocks/handlers";
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
});
