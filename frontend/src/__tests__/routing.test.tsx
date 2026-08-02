import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import AcceptInvitePage from "../pages/AcceptInvitePage";
import { server } from "../api/mocks/server";
import { setRefreshToken } from "../api/client";

function renderApp(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("routing", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("T-UI1 test_utente_non_autenticato_va_al_login: /notifications senza sessione porta a /login", async () => {
    renderApp("/notifications");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "NotifyHub" })).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("T-UI2 test_viewer_non_vede_la_voce_canali: viewer non vede il menu e la rotta è negata", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({
          id: "u1",
          email: "viewer@acme.test",
          role: "viewer",
          tenant_id: "t1",
          tenant_name: "ACME",
        }),
      ),
    );
    setRefreshToken("refresh-token-fixture");

    renderApp("/channels");

    await waitFor(() => {
      expect(screen.getByText(/accesso negato/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "Canali" })).not.toBeInTheDocument();
  });

  it("T-UI3 test_token_invito_letto_dal_frammento: il token va nel corpo, non nella query", async () => {
    let capturedBody: unknown = null;
    let capturedUrl = "";
    server.use(
      http.post("/api/v1/invitations/accept", async ({ request }) => {
        capturedUrl = request.url;
        capturedBody = await request.json();
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    window.location.hash = "#token=abc";

    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/invite"]}>
          <AcceptInvitePage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await user.type(screen.getByLabelText(/password/i), "password-lunga-123");
    await user.click(screen.getByRole("button", { name: "Attiva account" }));

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ token: "abc" });
    });
    expect(new URL(capturedUrl).searchParams.get("token")).toBeNull();

    window.location.hash = "";
  });
});
