import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../App";
import { setRefreshToken } from "../api/client";

// Il chunk della pagina Utenti arriva solo quando il test lo decide: così
// l'attesa del caricamento è misurabile e non dipende dai tempi del caricatore.
const chunk = vi.hoisted(() => {
  let apri: () => void = () => undefined;
  const pronto = new Promise<void>((resolve) => {
    apri = resolve;
  });
  return { pronto, apri: () => apri() };
});

vi.mock("../pages/UsersPage", async () => {
  await chunk.pronto;
  return { default: () => <h1>Utenti</h1> };
});

describe("caricamento delle pagine autenticate", () => {
  it("mentre arriva il chunk della pagina il menu resta a schermo", async () => {
    setRefreshToken("refresh-token-fixture");
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/users"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Il menu compare con la sessione; la pagina, ancora in attesa, mostra il
    // suo testo dentro l'area del menu, non in una cornice da login.
    const menu = await screen.findByRole("navigation", { name: "Navigazione principale" });
    expect(await screen.findByText("Caricamento…")).toBeInTheDocument();
    expect(menu).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Navigazione principale" })).toBeInTheDocument();

    chunk.apri();
    expect(await screen.findByRole("heading", { name: "Utenti" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Navigazione principale" })).toBeInTheDocument();
  });
});
