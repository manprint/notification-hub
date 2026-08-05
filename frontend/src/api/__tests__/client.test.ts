import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import {
  apiGet,
  apiPost,
  getRefreshToken,
  onLogout,
  setAccessToken,
  setRefreshToken,
} from "../client";
import type { ApiError } from "../types";
import { server } from "../mocks/server";

beforeEach(() => {
  setAccessToken(null);
  setRefreshToken(null);
});

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
});
