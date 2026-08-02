import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import GroupsPage from "../GroupsPage";
import { fixtureDeleteImpact } from "../../api/mocks/handlers";
import { renderWithProviders } from "./testUtils";

describe("GroupsPage", () => {
  it("T-UI12 test_cancellazione_gruppo_mostra_impatto: mostra i conteggi e richiede il nome esatto", async () => {
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

    const confirmButton = screen.getByRole("button", { name: "Conferma" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByLabelText(/digita/i), "Server Produzione");
    expect(confirmButton).toBeEnabled();
  });
});
