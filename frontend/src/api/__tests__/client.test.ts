import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  apiGet,
  apiPost,
  asApiError,
  getAccessToken,
  getRefreshToken,
  onLogout,
  setAccessToken,
  setRefreshToken,
  storeTokens,
  watchOtherTabs,
} from "../client";
import type { ApiError } from "../types";
import { server } from "../mocks/server";

beforeEach(() => {
  setAccessToken(null);
  localStorage.clear();
});

/** Un access token con la forma di un JWT: solo il claim `sub` conta qui. */
function jwtFor(sub: string): string {
  const payload = btoa(JSON.stringify({ sub })).replace(/=+$/, "");
  return `header.${payload}.firma`;
}

function tokenPair(sub: string, refresh: string) {
  return {
    access_token: jwtFor(sub),
    refresh_token: refresh,
    token_type: "bearer",
    expires_in: 900,
  };
}

/** L'evento che il browser recapita alle ALTRE schede quando una scrive in
 *  localStorage (nella scheda che scrive non arriva: in jsdom va simulato). */
function storageEventFromOtherTab(key: string | null, newValue: string | null) {
  window.dispatchEvent(new StorageEvent("storage", { key, newValue }));
}

describe("client", () => {
  it("test_refresh_una_sola_volta: 5 richieste 401 parallele producono un solo refresh", async () => {
    setAccessToken("expired-token");
    setRefreshToken("refresh-token-fixture");

    let refreshCalls = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json({
          access_token: "new-token",
          refresh_token: "new-refresh-token",
          token_type: "bearer",
          expires_in: 900,
        });
      }),
      http.get("/api/v1/probe", ({ request }) => {
        const auth = request.headers.get("authorization");
        if (auth === "Bearer new-token") return HttpResponse.json({ ok: true });
        return new HttpResponse(null, { status: 401 });
      }),
    );

    const results = await Promise.all(
      Array.from({ length: 5 }, () => apiGet<{ ok: boolean }>("/api/v1/probe")),
    );

    expect(results).toHaveLength(5);
    results.forEach((r) => expect(r.ok).toBe(true));
    expect(refreshCalls).toBe(1);
  });

  it("test_reload_con_refresh_token_non_invia_prima_una_richiesta_401", async () => {
    setRefreshToken("refresh-token-fixture");

    let refreshCalls = 0;
    let probeCalls = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json({
          access_token: "new-token",
          refresh_token: "new-refresh-token",
          token_type: "bearer",
          expires_in: 900,
        });
      }),
      http.get("/api/v1/probe", ({ request }) => {
        probeCalls += 1;
        expect(request.headers.get("authorization")).toBe("Bearer new-token");
        return HttpResponse.json({ ok: true });
      }),
    );

    await expect(apiGet<{ ok: boolean }>("/api/v1/probe")).resolves.toEqual({ ok: true });
    expect(refreshCalls).toBe(1);
    expect(probeCalls).toBe(1);
  });

  it("test_refresh_fallito_pulisce_la_sessione: refresh 401 rimuove il token ed emette logout", async () => {
    setAccessToken("expired-token");
    setRefreshToken("refresh-token-fixture");

    server.use(
      http.post("/api/v1/auth/refresh", () => new HttpResponse(null, { status: 401 })),
      http.get("/api/v1/probe", () => new HttpResponse(null, { status: 401 })),
    );

    let loggedOut = false;
    const unsubscribe = onLogout(() => {
      loggedOut = true;
    });

    await expect(apiGet("/api/v1/probe")).rejects.toBeTruthy();

    expect(loggedOut).toBe(true);
    expect(getRefreshToken()).toBeNull();
    unsubscribe();
  });

  it("test_refresh_offline_restituisce_api_error_senza_distruggere_la_sessione", async () => {
    setAccessToken("expired-token");
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.post("/api/v1/auth/refresh", () => HttpResponse.error()),
      http.get("/api/v1/probe", () => new HttpResponse(null, { status: 401 })),
    );

    await expect(apiGet("/api/v1/probe")).rejects.toMatchObject({
      status: 0,
      type: "/problems/network-unreachable",
    } satisfies Partial<ApiError>);
    expect(getRefreshToken()).toBe("refresh-token-fixture");
  });

  it("test_errore_problem_json_tradotto: un 422 RFC 7807 diventa un ApiError con detail", async () => {
    server.use(
      http.get("/api/v1/probe-422", () =>
        HttpResponse.json(
          {
            type: "/problems/validation-error",
            title: "Validation Error",
            status: 422,
            detail: "Request validation failed.",
          },
          { status: 422 },
        ),
      ),
    );

    await expect(apiGet("/api/v1/probe-422")).rejects.toMatchObject({
      status: 422,
      detail: "Request validation failed.",
    } satisfies Partial<ApiError>);
  });

  it("bulk_read_posts_body_and_succeeds: POST bulk-read invia il body ed e' risolto", async () => {
    let capturedBody: unknown;
    server.use(
      http.post("/api/v1/notifications/bulk-read", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({ marked_read: 0 });
      }),
    );

    const result = await apiPost<{ marked_read: number }>(
      "/api/v1/notifications/bulk-read",
      { group_id: "g1" },
    );

    expect(capturedBody).toEqual({ group_id: "g1" });
    expect(result).toEqual({ marked_read: 0 });
  });

  it("refresh con 5xx: l'errore arriva al chiamante e la sessione resta", async () => {
    setAccessToken("expired-token");
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.post("/api/v1/auth/refresh", () => new HttpResponse("Bad gateway", { status: 502 })),
      http.get("/api/v1/probe", () => new HttpResponse(null, { status: 401 })),
    );
    const loggedOut = vi.fn();
    const unsubscribe = onLogout(loggedOut);

    // Un proxy giu' non dice niente sulla validita' del token: buttarlo
    // costringeva a un nuovo login per un guasto passeggero.
    await expect(apiGet("/api/v1/probe")).rejects.toMatchObject({ status: 502 });
    expect(loggedOut).not.toHaveBeenCalled();
    expect(getRefreshToken()).toBe("refresh-token-fixture");
    unsubscribe();
  });

  it("refresh con 5xx al primo caricamento: nessun logout, token conservato", async () => {
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.post("/api/v1/auth/refresh", () => new HttpResponse(null, { status: 503 })),
    );

    await expect(apiGet("/api/v1/probe")).rejects.toMatchObject({ status: 503 });
    expect(getRefreshToken()).toBe("refresh-token-fixture");
  });

  it("refresh con 403: la sessione si chiude come per il 401", async () => {
    setAccessToken("expired-token");
    setRefreshToken("refresh-token-fixture");
    server.use(
      http.post("/api/v1/auth/refresh", () => new HttpResponse(null, { status: 403 })),
      http.get("/api/v1/probe", () => new HttpResponse(null, { status: 401 })),
    );
    const loggedOut = vi.fn();
    const unsubscribe = onLogout(loggedOut);

    await expect(apiGet("/api/v1/probe")).rejects.toMatchObject({ status: 401 });
    expect(loggedOut).toHaveBeenCalledTimes(1);
    expect(getRefreshToken()).toBeNull();
    unsubscribe();
  });

  it("401 senza refresh token (logout in un'altra scheda): logout locale", async () => {
    setAccessToken("access-di-prima");
    let refreshCalls = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json(tokenPair("u1", "r2"));
      }),
      http.get("/api/v1/probe", () => new HttpResponse(null, { status: 401 })),
    );
    const loggedOut = vi.fn();
    const unsubscribe = onLogout(loggedOut);

    await expect(apiGet("/api/v1/probe")).rejects.toMatchObject({ status: 401 });
    expect(loggedOut).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
    expect(refreshCalls).toBe(0);
    unsubscribe();
  });

  describe("fra piu' schede", () => {
    const originalLocks = Object.getOwnPropertyDescriptor(navigator, "locks");

    afterEach(() => {
      if (originalLocks) Object.defineProperty(navigator, "locks", originalLocks);
      else delete (navigator as { locks?: unknown }).locks;
    });

    it("il refresh passa dal lock e usa il token ruotato nel frattempo da un'altra scheda", async () => {
      setAccessToken("expired-token");
      setRefreshToken("token-vecchio");
      const request = vi.fn(async (_name: string, task: () => Promise<unknown>) => {
        // Mentre questa scheda aspettava il lock, un'altra ha ruotato.
        localStorage.setItem("notifyhub.refresh_token", "token-ruotato-altrove");
        return task();
      });
      Object.defineProperty(navigator, "locks", { value: { request }, configurable: true });

      const presented: unknown[] = [];
      server.use(
        http.post("/api/v1/auth/refresh", async ({ request: req }) => {
          presented.push(await req.json());
          return HttpResponse.json(tokenPair("u1", "token-nuovo"));
        }),
        http.get("/api/v1/probe", ({ request: req }) =>
          req.headers.get("authorization") === `Bearer ${jwtFor("u1")}`
            ? HttpResponse.json({ ok: true })
            : new HttpResponse(null, { status: 401 }),
        ),
      );

      await expect(apiGet("/api/v1/probe")).resolves.toEqual({ ok: true });
      expect(request).toHaveBeenCalledWith("notifyhub.refresh", expect.any(Function));
      // Mai il token vecchio: presentarlo e' il riuso che revoca la famiglia.
      expect(presented).toEqual([{ refresh_token: "token-ruotato-altrove" }]);
      expect(getRefreshToken()).toBe("token-nuovo");
    });

    it("se l'altra scheda ha fatto logout mentre si aspettava il lock, niente refresh", async () => {
      setAccessToken("expired-token");
      setRefreshToken("token-vecchio");
      const request = vi.fn(async (_name: string, task: () => Promise<unknown>) => {
        localStorage.removeItem("notifyhub.refresh_token");
        return task();
      });
      Object.defineProperty(navigator, "locks", { value: { request }, configurable: true });
      let refreshCalls = 0;
      server.use(
        http.post("/api/v1/auth/refresh", () => {
          refreshCalls += 1;
          return HttpResponse.json(tokenPair("u1", "r2"));
        }),
        http.get("/api/v1/probe", () => new HttpResponse(null, { status: 401 })),
      );
      const loggedOut = vi.fn();
      const unsubscribe = onLogout(loggedOut);

      await expect(apiGet("/api/v1/probe")).rejects.toMatchObject({ status: 401 });
      expect(refreshCalls).toBe(0);
      expect(loggedOut).toHaveBeenCalledTimes(1);
      unsubscribe();
    });

    it("un login in un'altra scheda durante il refresh non viene cancellato dal suo 401", async () => {
      setAccessToken("expired-token");
      setRefreshToken("token-di-a");
      const presented: unknown[] = [];
      server.use(
        http.post("/api/v1/auth/refresh", async ({ request: req }) => {
          const body = (await req.json()) as { refresh_token: string };
          presented.push(body);
          if (body.refresh_token === "token-di-a") {
            // Mentre la risposta viaggia, l'altra scheda fa logout e login:
            // il token di A è ormai revocato.
            storeTokens(tokenPair("utente-b", "token-di-b"));
            return new HttpResponse(null, { status: 401 });
          }
          return HttpResponse.json(tokenPair("utente-b", "token-di-b-ruotato"));
        }),
        http.get("/api/v1/probe", ({ request: req }) =>
          req.headers.get("authorization") === `Bearer ${jwtFor("utente-b")}`
            ? HttpResponse.json({ ok: true })
            : new HttpResponse(null, { status: 401 }),
        ),
      );
      const loggedOut = vi.fn();
      const unsubscribe = onLogout(loggedOut);

      await expect(apiGet("/api/v1/probe")).resolves.toEqual({ ok: true });
      // Il 401 riguardava la sessione di prima: cancellare tutto avrebbe buttato
      // fuori anche l'altra scheda, appena entrata.
      expect(loggedOut).not.toHaveBeenCalled();
      expect(presented).toEqual([{ refresh_token: "token-di-a" }, { refresh_token: "token-di-b" }]);
      expect(getRefreshToken()).toBe("token-di-b-ruotato");
      unsubscribe();
    });

    it("refresh token rimosso da un'altra scheda: logout locale", () => {
      storeTokens(tokenPair("u1", "r1"));
      const loggedOut = vi.fn();
      const unsubscribe = onLogout(loggedOut);
      const stop = watchOtherTabs(vi.fn());

      localStorage.removeItem("notifyhub.refresh_token");
      storageEventFromOtherTab("notifyhub.refresh_token", null);

      expect(loggedOut).toHaveBeenCalledTimes(1);
      expect(getAccessToken()).toBeNull();
      stop();
      unsubscribe();
    });

    it("login di un altro utente in un'altra scheda: si butta l'access token e si avvisa", () => {
      storeTokens(tokenPair("utente-a", "r-a"));
      const onUserSwitch = vi.fn();
      const stop = watchOtherTabs(onUserSwitch);

      // Come scrive storeTokens nell'altra scheda: prima il proprietario.
      localStorage.setItem("notifyhub.session_user", "utente-b");
      localStorage.setItem("notifyhub.refresh_token", "r-b");
      storageEventFromOtherTab("notifyhub.refresh_token", "r-b");

      expect(onUserSwitch).toHaveBeenCalledTimes(1);
      // Restare "A" con in memoria il token di A e in localStorage quello di B
      // voleva dire, al primo refresh, dati di B sotto il nome di A.
      expect(getAccessToken()).toBeNull();
      stop();
    });

    it("rotazione fatta da un'altra scheda dello stesso utente: nessun effetto", () => {
      storeTokens(tokenPair("utente-a", "r-a"));
      const onUserSwitch = vi.fn();
      const loggedOut = vi.fn();
      const unsubscribe = onLogout(loggedOut);
      const stop = watchOtherTabs(onUserSwitch);

      localStorage.setItem("notifyhub.refresh_token", "r-a2");
      storageEventFromOtherTab("notifyhub.refresh_token", "r-a2");

      expect(onUserSwitch).not.toHaveBeenCalled();
      expect(loggedOut).not.toHaveBeenCalled();
      expect(getAccessToken()).toBe(jwtFor("utente-a"));
      stop();
      unsubscribe();
    });

    it("storeTokens scrive il proprietario prima del refresh token", () => {
      const writes: string[] = [];
      const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
        this: Storage,
        key: string,
      ) {
        writes.push(key);
      });
      storeTokens(tokenPair("utente-a", "r-a"));
      setItem.mockRestore();

      expect(writes).toEqual(["notifyhub.session_user", "notifyhub.refresh_token"]);
    });
  });

  it("gli endpoint senza sessione non mandano il Bearer e un loro 401 non avvia il refresh", async () => {
    setAccessToken("access-di-una-sessione");
    setRefreshToken("refresh-token-fixture");
    let refreshCalls = 0;
    const authHeaders: (string | null)[] = [];
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json(tokenPair("u1", "r2"));
      }),
      http.post("/api/v1/invitations/accept", ({ request }) => {
        authHeaders.push(request.headers.get("authorization"));
        return HttpResponse.json({ detail: "Invalid invitation." }, { status: 401 });
      }),
      http.post("/api/v1/auth/login", ({ request }) => {
        authHeaders.push(request.headers.get("authorization"));
        return HttpResponse.json({ detail: "Invalid credentials." }, { status: 401 });
      }),
    );
    const loggedOut = vi.fn();
    const unsubscribe = onLogout(loggedOut);

    await expect(
      apiPost("/api/v1/invitations/accept", { token: "t", password: "p" }),
    ).rejects.toMatchObject({ status: 401, detail: "Invalid invitation." });
    await expect(
      apiPost("/api/v1/auth/login", { email: "a@b.c", password: "p" }),
    ).rejects.toMatchObject({ status: 401, detail: "Invalid credentials." });

    expect(authHeaders).toEqual([null, null]);
    expect(refreshCalls).toBe(0);
    expect(loggedOut).not.toHaveBeenCalled();
    expect(getRefreshToken()).toBe("refresh-token-fixture");
    unsubscribe();
  });

  it("errore non-JSON senza statusText (HTTP/2): il titolo dice lo stato", async () => {
    // Direttamente su fetch: MSW riempie da se' lo statusText mancante, mentre
    // una risposta HTTP/2 vera arriva con la stringa vuota.
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response("<html>bad gateway</html>", { status: 502, statusText: "" }),
      );

    await expect(apiGet("/api/v1/probe-502")).rejects.toMatchObject({
      status: 502,
      title: "Errore HTTP 502",
      detail: "",
    } satisfies Partial<ApiError>);
    fetchSpy.mockRestore();
  });

  it("una richiesta partita con il token A che riceve 401 dopo un rinnovo riparte col token B, senza un nuovo refresh", async () => {
    setAccessToken("token-A");
    setRefreshToken("refresh-token-fixture");

    const authHeaders: Array<string | null> = [];
    let refreshCalls = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json(tokenPair("u1", "refresh-nuovo"));
      }),
      http.get("/api/v1/probe-tardiva", ({ request }) => {
        const auth = request.headers.get("authorization");
        authHeaders.push(auth);
        if (auth === "Bearer token-A") {
          // Mentre la risposta 401 è in volo, la sessione viene rinnovata altrove.
          setAccessToken("token-B");
          return new HttpResponse(null, { status: 401 });
        }
        return HttpResponse.json({ ok: true });
      }),
    );

    await expect(apiGet("/api/v1/probe-tardiva")).resolves.toEqual({ ok: true });
    expect(authHeaders).toEqual(["Bearer token-A", "Bearer token-B"]);
    expect(refreshCalls).toBe(0);
  });

  it("se la lettura del corpo cade a metà l'errore ha titolo e stato, non un TypeError", async () => {
    setAccessToken("token");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("{", { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    const errore = await apiGet("/api/v1/probe-corpo").catch((e: unknown) => e);
    expect(errore).toMatchObject({ status: 0, type: "/problems/network-unreachable" });
    expect((errore as ApiError).title).not.toBe("");
    fetchSpy.mockRestore();
  });

  it("asApiError rende leggibile anche un errore che non è di NotifyHub", () => {
    expect(asApiError(new TypeError("network error"))).toMatchObject({
      status: 0,
      title: "Errore imprevisto",
    });
    const gia: ApiError = { status: 409, type: "/problems/conflict", title: "Conflict", detail: "", extra: {} };
    expect(asApiError(gia)).toBe(gia);
  });
});
