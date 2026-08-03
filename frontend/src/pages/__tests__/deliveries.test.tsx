import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import DeliveriesPage from "../DeliveriesPage";
import { setRefreshToken } from "../../api/client";
import { renderWithProviders } from "./testUtils";

describe("DeliveriesPage", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture"); // fixtureMe di default ha ruolo owner
  });

  it("T-UI17 test_retry_solo_su_dead: il pulsante compare solo sulle righe dead", async () => {
    renderWithProviders(<DeliveriesPage />);

    await waitFor(() => {
      expect(screen.getByText("Morta")).toBeInTheDocument();
    });

    const rows = screen.getAllByRole("row").slice(1); // salta l'intestazione
    const retryButtons = screen.queryAllByRole("button", { name: "Ri-accoda" });
    expect(retryButtons).toHaveLength(1);

    const deadRow = rows.find((row) => row.textContent?.includes("Morta"));
    const sentRow = rows.find((row) => row.textContent?.includes("Inviata"));
    expect(deadRow?.querySelector("button")).not.toBeNull();
    expect(sentRow?.querySelector("button")).toBeNull();
  });
});

describe("DeliveriesPage leggibilità", () => {
  beforeEach(() => {
    localStorage.clear();
    setRefreshToken("refresh-token-fixture");
  });

  it("ogni riga dice quale notifica è stata inoltrata e verso quale canale", async () => {
    renderWithProviders(<DeliveriesPage />);

    await waitFor(() => {
      expect(screen.getByText("Morta")).toBeInTheDocument();
    });

    // canale di destinazione e receiver di origine, non solo id opachi
    expect(screen.getAllByText("Slack #ops").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Backup notturno/).length).toBeGreaterThan(0);

    // l'anteprima è un link alla notifica inoltrata
    const preview = screen.getByRole("link", { name: "Backup FALLITO: disco pieno su /var" });
    expect(preview).toHaveAttribute("href", "/notifications/n1");
  });
});
