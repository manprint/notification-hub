import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import GroupsPage from "../GroupsPage";
import { setRefreshToken } from "../../api/client";
import { fixtureDeleteImpact } from "../../api/mocks/handlers";
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

    const confirmButton = screen.getByRole("button", { name: "Conferma" });
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

    expect(screen.getAllByRole("button", { name: "Apri" })).toHaveLength(2);

    const g1Row = screen.getByRole("row", { name: /server produzione/i });
    expect(within(g1Row).getByText("1")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Cerca gruppi"), "backup");
    expect(screen.queryByText("Server Produzione")).toBeNull();
    expect(screen.getByRole("row", { name: /backup/i })).toBeInTheDocument();
  });
});
