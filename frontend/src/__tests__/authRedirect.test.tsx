// Il giro completo fra rotte protette e login: dove si torna dopo l'accesso,
// cosa succede a un indirizzo che non esiste, chi è già dentro.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { setAccessToken, setRefreshToken } from "../api/client";

function Posizione() {
  const location = useLocation();
  return <output data-testid="posizione">{`${location.pathname}${location.search}`}</output>;
}

function renderApp(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
        <Posizione />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("redirect di autenticazione", () => {
  beforeEach(() => {
    setAccessToken(null);
    localStorage.clear();
  });

  it("dopo il login si torna alla pagina chiesta, non al riepilogo", async () => {
    const user = userEvent.setup();
    renderApp("/deliveries?status=dead");

    await screen.findByRole("heading", { name: "NotifyHub" });
    expect(screen.getByTestId("posizione")).toHaveTextContent("/login");

    await user.type(screen.getByLabelText("Email"), "owner@acme.test");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Accedi" }));

    await screen.findByRole("button", { name: "Esci" });
    expect(screen.getByTestId("posizione")).toHaveTextContent("/deliveries?status=dead");
  });

  it("un indirizzo che non esiste mostra «pagina non trovata» con il link alla home", async () => {
    setRefreshToken("refresh-token-fixture");
    renderApp("/indirizzo-che-non-esiste");

    expect(await screen.findByRole("heading", { name: "Pagina non trovata" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Torna al riepilogo" })).toHaveAttribute("href", "/");
  });

  it("chi è già autenticato non vede il form di login: torna dentro", async () => {
    setRefreshToken("refresh-token-fixture");
    renderApp("/login");

    // Rientrare come un altro utente sopra la sessione aperta lasciava token e
    // cache del primo sotto il nome del secondo: si passa da "Esci".
    await screen.findByRole("button", { name: "Esci" });
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(screen.getByTestId("posizione")).toHaveTextContent(/^\/$/);
  });
});
