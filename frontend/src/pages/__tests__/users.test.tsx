import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import UsersPage from "../UsersPage";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

describe("UsersPage", () => {
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
});
