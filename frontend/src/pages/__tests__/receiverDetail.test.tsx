import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import ReceiverDetailPage from "../ReceiverDetailPage";
import { setRefreshToken } from "../../api/client";
import { fixtureTestSeverityRule } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

function renderReceiverDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/receivers/:id" element={<ReceiverDetailPage />} />
    </Routes>,
    ["/receivers/r1"],
  );
}

describe("ReceiverDetailPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("T-UI13 test_prova_severity_mostra_regola: la risposta di prova mostra la regola vincente", async () => {
    const user = userEvent.setup();
    renderReceiverDetail();

    await waitFor(() => {
      expect(screen.getByText(/Contenuto di prova/)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/contenuto di prova/i), "Backup FALLITO");
    await user.click(screen.getByRole("button", { name: "Esegui prova" }));

    await waitFor(() => {
      expect(screen.getByText(/Severity risolta/).closest("p")?.textContent).toContain(
        fixtureTestSeverityRule.matched_pattern,
      );
    });
  });

  it("T-UI14 test_rotate_slug_nascosto_al_member: con ruolo member il pulsante non è nel documento", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: "u1",
          email: "member@acme.test",
          role: "member",
          tenant_id: "t1",
          tenant_name: "ACME",
        }),
      ),
    );
    setRefreshToken("refresh-token-fixture");

    renderReceiverDetail();

    await waitFor(() => {
      expect(screen.getByText(/Slug:/)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Rigenera slug" })).not.toBeInTheDocument();
  });
});
