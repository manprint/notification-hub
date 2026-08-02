import { screen, waitFor } from "@testing-library/react";
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
});
