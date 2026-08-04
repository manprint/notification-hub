// Pagina di accesso: se si rompe, nessuno entra. Era coperta al 74% sulle righe
// ma al **14% sui rami**, cioe' del comportamento vero (credenziali sbagliate,
// rate limit, doppio invio) non era verificato niente.

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import LoginPage from "../LoginPage";
import { getAccessToken, getRefreshToken } from "../../api/client";
import { fixtureTokenPair } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

async function compilaEInvia(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Email"), "owner@acme.test");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
  await user.click(screen.getByRole("button", { name: "Accedi" }));
}

describe("LoginPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("accesso riuscito: conserva i token e non mostra errori", async () => {
    const user = userEvent.setup();
    let inviato: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/auth/login", async ({ request }) => {
        inviato = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(fixtureTokenPair);
      }),
    );

    renderWithProviders(<LoginPage />);
    await compilaEInvia(user);

    await waitFor(() => expect(inviato).not.toBeNull());
    expect(inviato).toEqual({
      email: "owner@acme.test",
      password: "correct-horse-battery",
    });
    await waitFor(() => expect(getAccessToken()).toBe(fixtureTokenPair.access_token));
    // Il refresh token va in localStorage: e' cio' che tiene la sessione al
    // ricaricamento della pagina.
    expect(getRefreshToken()).toBe(fixtureTokenPair.refresh_token);
    expect(screen.queryByText(/Troppi tentativi/)).not.toBeInTheDocument();
  });

  it("credenziali sbagliate: mostra il messaggio e non conserva nulla", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            type: "/problems/unauthorized",
            title: "Unauthorized",
            status: 401,
            detail: "Invalid credentials.",
          },
          { status: 401 },
        ),
      ),
    );

    renderWithProviders(<LoginPage />);
    await compilaEInvia(user);

    expect(await screen.findByText(/Invalid credentials/)).toBeInTheDocument();
    expect(getRefreshToken()).toBeNull();
    // Il pulsante torna disponibile: un errore non deve lasciare il form bloccato.
    expect(screen.getByRole("button", { name: "Accedi" })).toBeEnabled();
  });

  it("troppi tentativi: messaggio dedicato coi minuti di attesa", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            type: "/problems/rate-limited",
            title: "Too Many Requests",
            status: 429,
            detail: "Too many login attempts. Please try again later.",
            retry_after: 900,
          },
          { status: 429 },
        ),
      ),
    );

    renderWithProviders(<LoginPage />);
    await compilaEInvia(user);

    // 900 secondi arrotondati per eccesso: "15 minuti", non "900".
    expect(await screen.findByText(/Troppi tentativi, riprova fra 15 minuti/)).toBeInTheDocument();
  });

  it("rate limit senza retry_after: non mostra «NaN minuti»", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            type: "/problems/rate-limited",
            title: "Too Many Requests",
            status: 429,
            detail: "Too many login attempts.",
          },
          { status: 429 },
        ),
      ),
    );

    renderWithProviders(<LoginPage />);
    await compilaEInvia(user);

    expect(await screen.findByText(/riprova fra qualche minuti/)).toBeInTheDocument();
  });

  it("il pulsante si disabilita durante l'invio: niente doppio login", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.post("/api/v1/auth/login", async () => {
        chiamate += 1;
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json(fixtureTokenPair);
      }),
    );

    renderWithProviders(<LoginPage />);
    await user.type(screen.getByLabelText("Email"), "owner@acme.test");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");

    const pulsante = screen.getByRole("button", { name: "Accedi" });
    await user.click(pulsante);
    expect(pulsante).toBeDisabled();

    await waitFor(() => expect(getAccessToken()).toBe(fixtureTokenPair.access_token));
    expect(chiamate).toBe(1);
  });

  it("un guasto del server non lascia la pagina muta", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/auth/login", () => HttpResponse.error()),
    );

    renderWithProviders(<LoginPage />);
    await compilaEInvia(user);

    // Prima della correzione qui la pagina andava in schermata bianca:
    // `error.extra.retry_after` su un errore di rete, che non ha `extra`.
    // Ora l'utente legge cosa e' successo e il form resta usabile.
    expect(
      await screen.findByText(/Impossibile contattare NotifyHub/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accedi" })).toBeEnabled();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });
});
