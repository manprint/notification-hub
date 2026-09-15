import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import HomePage from "../HomePage";
import { fixtureStatsSummary } from "../../api/mocks/handlers";
import { renderWithProviders } from "./testUtils";

describe("HomePage", () => {
  it("T-UI6 test_home_mostra_conteggi: mostra i conteggi e cinque severity", async () => {
    renderWithProviders(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText(String(fixtureStatsSummary.total_unread))).toBeInTheDocument();
    });

    expect(document.querySelectorAll(".severity-badge")).toHaveLength(5);
    expect(Object.keys(fixtureStatsSummary.by_severity)).toHaveLength(5);
  });

  it("T-UI22 test_riepilogo_espande_i_receiver: i receiver del gruppo compaiono solo da aperti", async () => {
    renderWithProviders(<HomePage />);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Server Produzione" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "Backup notturno" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /mostra i receiver di server produzione/i }));

    const receiver = await screen.findByRole("link", { name: "Backup notturno" });
    // Riga cliccabile: porta alle notifiche del gruppo gia' filtrate su quel receiver.
    expect(receiver).toHaveAttribute("href", "/notifications?group_id=g1&receiver_id=r1");
    // Un receiver che non ha mai scritto resta in elenco, marcato come disabilitato.
    expect(screen.getByRole("link", { name: "Job mai partito" })).toBeInTheDocument();
    expect(screen.getByText("disabilitato")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /nascondi i receiver di server produzione/i }));
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Backup notturno" })).not.toBeInTheDocument();
    });
  });

  it("T-UI23 test_gruppo_senza_receiver_non_ha_toggle: niente freccia su un gruppo vuoto", async () => {
    renderWithProviders(<HomePage />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Backup" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /receiver di backup/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Backup" })).toHaveAttribute(
      "href",
      "/notifications?group_id=g2",
    );
  });
});
