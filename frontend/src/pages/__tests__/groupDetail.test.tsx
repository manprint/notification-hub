import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GroupDetailPage from "../GroupDetailPage";
import ReceiverDetailPage from "../ReceiverDetailPage";
import { setRefreshToken } from "../../api/client";
import { copyText } from "../../lib/clipboard";
import { fixtureReceiver } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { HttpResponse, http } from "msw";
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

    await user.click(screen.getByRole("button", { name: "Copia slug" }));

    expect(copyText).toHaveBeenCalledWith(fixtureReceiver.slug);
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
  it("T-GRP8 il conteggio e il vuoto non mentono mentre i receiver caricano o non si leggono", async () => {
    let rispondi: () => void = () => undefined;
    server.use(
      http.get("/api/v1/groups/g1/receivers", async () => {
        await new Promise<void>((resolve) => {
          rispondi = resolve;
        });
        return HttpResponse.json([]);
      }),
    );
    renderGroupDetail();

    expect(await screen.findByText("Caricamento…")).toBeInTheDocument();
    expect(screen.queryByText(/configurati/)).not.toBeInTheDocument();

    rispondi();
    expect(await screen.findByText("Nessun receiver in questo gruppo.")).toBeInTheDocument();
    expect(screen.getByText("0 configurati")).toBeInTheDocument();
  });

  it("T-GRP9 se i receiver non si leggono non dice che il gruppo è vuoto", async () => {
    server.use(
      http.get("/api/v1/groups/g1/receivers", () =>
        HttpResponse.json(
          { type: "/problems/internal", title: "Internal", status: 500, detail: "Boom." },
          { status: 500 },
        ),
      ),
    );
    renderGroupDetail();

    expect(await screen.findByText(/Elenco non disponibile/)).toBeInTheDocument();
    expect(screen.queryByText("Nessun receiver in questo gruppo.")).not.toBeInTheDocument();
    expect(screen.queryByText(/configurati/)).not.toBeInTheDocument();
  });
});
