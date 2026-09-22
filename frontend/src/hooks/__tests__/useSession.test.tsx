// La sessione è ciò che separa i dati di un utente da quelli del successivo
// sullo stesso browser: logout che revoca davvero, cache svuotata, schede che
// non restano "A" con i token di "B".

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import {
  apiGet,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
  storeTokens,
} from "../../api/client";
import { fixtureMe, fixtureTokenPair } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { SessionProvider, useSession } from "../useSession";

function jwtFor(sub: string): string {
  return `header.${btoa(JSON.stringify({ sub })).replace(/=+$/, "")}.firma`;
}

function Sonda() {
  const { user, loading, login, logout, reloadProfile } = useSession();
  return (
    <div>
      <p>{loading ? "caricamento" : user ? `utente:${user.email}:${user.role}` : "nessuno"}</p>
      <button onClick={() => void login("owner@acme.test", "password-lunga-123").catch(() => {})}>
        entra
      </button>
      <button onClick={() => void logout()}>esci</button>
      <button onClick={() => void reloadProfile()}>ricarica</button>
    </div>
  );
}

function renderSession() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <Sonda />
      </SessionProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

beforeEach(() => {
  setAccessToken(null);
  localStorage.clear();
});

describe("useSession", () => {
  it("il logout manda il refresh token al server, poi azzera token e cache", async () => {
    setRefreshToken("refresh-da-revocare");
    let body: unknown = null;
    let tokenAllaRichiesta: string | null = null;
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ ...fixtureTokenPair, refresh_token: "refresh-da-revocare" }),
      ),
      http.post("/api/v1/auth/logout", async ({ request }) => {
        body = await request.json();
        tokenAllaRichiesta = getRefreshToken();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    const queryClient = renderSession();
    await screen.findByText("utente:owner@acme.test:owner");
    queryClient.setQueryData(["notifications"], ["dati di A"]);

    await user.click(screen.getByRole("button", { name: "esci" }));

    await screen.findByText("nessuno");
    // `{}` non revocava niente: il token restava valido per tutta la sua durata.
    expect(body).toEqual({ refresh_token: "refresh-da-revocare" });
    // Al momento della richiesta il token c'era ancora: si revoca prima di
    // dimenticarlo, non dopo.
    expect(tokenAllaRichiesta).toBe("refresh-da-revocare");
    expect(getRefreshToken()).toBeNull();
    expect(getAccessToken()).toBeNull();
    expect(queryClient.getQueryData(["notifications"])).toBeUndefined();
  });

  it("il logout forzato dal client (refresh rifiutato) svuota la cache", async () => {
    setRefreshToken("refresh-token-fixture");
    const queryClient = renderSession();
    await screen.findByText("utente:owner@acme.test:owner");
    queryClient.setQueryData(["users"], ["dati di A"]);

    server.use(
      http.post("/api/v1/auth/refresh", () => new HttpResponse(null, { status: 401 })),
      http.get("/api/v1/probe", () => new HttpResponse(null, { status: 401 })),
    );
    await act(async () => {
      await apiGet("/api/v1/probe").catch(() => undefined);
    });

    await screen.findByText("nessuno");
    expect(queryClient.getQueryData(["users"])).toBeUndefined();
  });

  it("il login svuota la cache prima di caricare il profilo", async () => {
    const queryClient = renderSession();
    queryClient.setQueryData(["groups"], ["gruppi di chi c'era prima"]);
    let cacheAlMe: unknown = "non letto";
    server.use(
      http.get("/api/v1/auth/me", () => {
        cacheAlMe = queryClient.getQueryData(["groups"]);
        return HttpResponse.json(fixtureMe);
      }),
    );

    await userEvent.setup().click(screen.getByRole("button", { name: "entra" }));

    await screen.findByText("utente:owner@acme.test:owner");
    expect(cacheAlMe).toBeUndefined();
  });

  it("se /me fallisce dopo il login i token non restano salvati", async () => {
    server.use(
      http.get("/api/v1/auth/me", () =>
        HttpResponse.json({ detail: "Errore interno." }, { status: 500 }),
      ),
    );
    renderSession();

    await userEvent.setup().click(screen.getByRole("button", { name: "entra" }));

    await screen.findByText("nessuno");
    // Tenerli lasciava una sessione mai mostrata che si riapriva da sola al
    // caricamento successivo della pagina.
    await waitFor(() => expect(getRefreshToken()).toBeNull());
    expect(getAccessToken()).toBeNull();
  });

  it("logout in un'altra scheda: questa scheda esce e dimentica i dati", async () => {
    setRefreshToken("refresh-token-fixture");
    const queryClient = renderSession();
    await screen.findByText("utente:owner@acme.test:owner");
    queryClient.setQueryData(["notifications"], ["dati di A"]);

    act(() => {
      localStorage.removeItem("notifyhub.refresh_token");
      window.dispatchEvent(
        new StorageEvent("storage", { key: "notifyhub.refresh_token", newValue: null }),
      );
    });

    await screen.findByText("nessuno");
    expect(queryClient.getQueryData(["notifications"])).toBeUndefined();
  });

  it("login di un altro utente in un'altra scheda: la sessione si ricarica come quell'utente", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json({ ...fixtureTokenPair, access_token: jwtFor("utente-a") }),
      ),
      http.get("/api/v1/auth/me", ({ request }) =>
        request.headers.get("authorization") === `Bearer ${jwtFor("utente-b")}`
          ? HttpResponse.json({ ...fixtureMe, id: "utente-b", email: "b@acme.test", role: "viewer" })
          : HttpResponse.json({ ...fixtureMe, id: "utente-a" }),
      ),
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ ...fixtureTokenPair, access_token: jwtFor("utente-b") }),
      ),
    );
    const queryClient = renderSession();
    await userEvent.setup().click(screen.getByRole("button", { name: "entra" }));
    await screen.findByText("utente:owner@acme.test:owner");
    queryClient.setQueryData(["notifications"], ["dati di A"]);

    act(() => {
      // Ciò che storeTokens scrive nell'altra scheda al login di B.
      localStorage.setItem("notifyhub.session_user", "utente-b");
      localStorage.setItem("notifyhub.refresh_token", "refresh-di-b");
      window.dispatchEvent(
        new StorageEvent("storage", { key: "notifyhub.refresh_token", newValue: "refresh-di-b" }),
      );
    });

    await screen.findByText("utente:b@acme.test:viewer");
    expect(queryClient.getQueryData(["notifications"])).toBeUndefined();
    expect(getAccessToken()).toBe(jwtFor("utente-b"));
  });

  it("reloadProfile ruota i token e rilegge il ruolo", async () => {
    storeTokens(fixtureTokenPair);
    let refreshCalls = 0;
    let role = "owner";
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json(fixtureTokenPair);
      }),
      http.get("/api/v1/auth/me", () => HttpResponse.json({ ...fixtureMe, role })),
    );
    renderSession();
    await screen.findByText("utente:owner@acme.test:owner");
    const refreshBefore = refreshCalls;

    role = "admin";
    await userEvent.setup().click(screen.getByRole("button", { name: "ricarica" }));

    await screen.findByText("utente:owner@acme.test:admin");
    // Il backend autorizza col ruolo dentro l'access token: senza un refresh la
    // UI direbbe "admin" e il server continuerebbe a trattarlo da owner.
    expect(refreshCalls).toBe(refreshBefore + 1);
  });
});
