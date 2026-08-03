import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import ChannelsPage from "../ChannelsPage";
import { setRefreshToken } from "../../api/client";
import { renderWithProviders } from "./testUtils";

const FULL_WEBHOOK_URL = "https://hooks.slack.com/services/T0/B0/X0";

describe("ChannelsPage", () => {
  it("T-UI15 test_webhook_mai_in_chiaro: l'URL completa non compare in nessun testo né in alcun value", async () => {
    setRefreshToken("refresh-token-fixture");
    renderWithProviders(<ChannelsPage />);

    await waitFor(() => {
      expect(screen.getAllByText("Slack #ops").length).toBeGreaterThan(0);
    });

    expect(document.body.textContent).not.toContain(FULL_WEBHOOK_URL);
    for (const input of Array.from(document.querySelectorAll("input"))) {
      expect((input as HTMLInputElement).value).not.toContain(FULL_WEBHOOK_URL);
    }
  });

  it("T-UI16 test_mute_nasconde_la_soglia: scegliendo mute il campo min_severity sparisce", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderWithProviders(<ChannelsPage />);

    await waitFor(() => {
      expect(screen.getAllByText("Slack #ops").length).toBeGreaterThan(0);
    });

    expect(screen.getByLabelText(/soglia minima/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/modalità/i), "mute");

    expect(screen.queryByLabelText(/soglia minima/i)).not.toBeInTheDocument();
  });
});
