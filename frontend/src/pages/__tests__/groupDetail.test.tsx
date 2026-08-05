import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GroupDetailPage from "../GroupDetailPage";
import ReceiverDetailPage from "../ReceiverDetailPage";
import { setRefreshToken } from "../../api/client";
import { copyText } from "../../lib/clipboard";
import { fixtureReceiver } from "../../api/mocks/handlers";
import { renderWithProviders } from "./testUtils";

vi.mock("../../lib/clipboard", () => ({
  copyText: vi.fn().mockResolvedValue(undefined),
}));

// renderWithProviders monta solo un MemoryRouter (testUtils.tsx:7-15): senza un
// <Route> il parametro :id non viene popolato e le query (enabled: Boolean(id))
// non partono mai. Il wrapper segue il pattern di receiverDetail.test.tsx:16-23.
function renderGroupDetail(initialEntries = ["/groups/g1"]) {
  return renderWithProviders(
    <Routes>
      <Route path="/groups/:id" element={<GroupDetailPage />} />
      <Route path="/receivers/:id" element={<ReceiverDetailPage />} />
    </Routes>,
    initialEntries,
  );
}

describe("GroupDetailPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("T-GRP3 test_tabella_receiver_slug_e_copia: mostra slug troncato e copia lo slug completo", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderGroupDetail();

    await waitFor(() => {
      expect(screen.getByText("Server Produzione")).toBeInTheDocument();
    });

    const nameLink = screen.getByRole("link", { name: "Backup notturno" });
    expect(nameLink).toHaveAttribute("href", "/receivers/r1");

    const slug = fixtureReceiver.slug;
    const slugCell = screen.getByText(slug, { selector: "code" });
    expect(slugCell).toHaveAttribute("title", slug);

    await user.click(screen.getByRole("button", { name: "Copia" }));

    expect(copyText).toHaveBeenCalledWith(fixtureReceiver.ingest_url);
    expect(await screen.findByText("Copiato!")).toBeInTheDocument();
  });

  it("T-GRP4 test_click_nome_apre_dettaglio_receiver: il nome naviga a /receivers/:id", async () => {
    setRefreshToken("refresh-token-fixture");
    const user = userEvent.setup();
    renderGroupDetail();

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Backup notturno" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("link", { name: "Backup notturno" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Backup notturno" }),
      ).toBeInTheDocument();
    });
  });
});