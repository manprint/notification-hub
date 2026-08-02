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
});
