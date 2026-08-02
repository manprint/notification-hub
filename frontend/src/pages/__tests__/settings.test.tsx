import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import SettingsPage from "../SettingsPage";
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
});
