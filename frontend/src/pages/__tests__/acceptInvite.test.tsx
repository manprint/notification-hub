// L'unico modulo in cui si sceglie una password: se passa una password troppo
// corta o battuta male, l'utente resta fuori dall'account appena attivato.

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import AcceptInvitePage from "../AcceptInvitePage";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

describe("AcceptInvitePage", () => {
  beforeEach(() => {
    localStorage.clear();
    window.location.hash = "#token=abc";
  });

  afterEach(() => {
    window.location.hash = "";
  });

  it("rifiuta una password troppo corta senza chiamare l'API", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.post("/api/v1/invitations/accept", () => {
        chiamate += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderWithProviders(<AcceptInvitePage />);
    await user.type(screen.getByLabelText("Scegli una password"), "corta");
    await user.type(screen.getByLabelText("Ripeti la password"), "corta");
    await user.click(screen.getByRole("button", { name: "Attiva account" }));

    expect(await screen.findByText(/almeno 12 caratteri\./)).toBeInTheDocument();
    expect(screen.getByLabelText("Scegli una password")).toHaveAttribute("aria-invalid", "true");
    expect(chiamate).toBe(0);
  });

  it("rifiuta due password diverse e lo dice sul campo sbagliato", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.post("/api/v1/invitations/accept", () => {
        chiamate += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderWithProviders(<AcceptInvitePage />);
    await user.type(screen.getByLabelText("Scegli una password"), "password-lunga-123");
    await user.type(screen.getByLabelText("Ripeti la password"), "password-lunga-124");
    await user.click(screen.getByRole("button", { name: "Attiva account" }));

    expect(await screen.findByText(/non coincidono/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ripeti la password")).toHaveAttribute("aria-invalid", "true");
    expect(chiamate).toBe(0);
  });

  it("con il token nel frammento attiva l'account e lo dice", async () => {
    const user = userEvent.setup();
    let corpo: unknown = null;
    server.use(
      http.post("/api/v1/invitations/accept", async ({ request }) => {
        corpo = await request.json();
        return HttpResponse.json({}, { status: 201 });
      }),
    );

    renderWithProviders(<AcceptInvitePage />);
    await user.type(screen.getByLabelText("Scegli una password"), "password-lunga-123");
    await user.type(screen.getByLabelText("Ripeti la password"), "password-lunga-123");
    await user.click(screen.getByRole("button", { name: "Attiva account" }));

    await waitFor(() => expect(corpo).toMatchObject({ token: "abc" }));
    // Dopo il redirect al login serve sapere perché si è finiti lì.
    expect(await screen.findByText(/Account attivato/)).toBeInTheDocument();
  });

  it("senza token nel collegamento lo dice invece di provare l'attivazione", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.post("/api/v1/invitations/accept", () => {
        chiamate += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    window.location.hash = "";

    renderWithProviders(<AcceptInvitePage />);
    await user.type(screen.getByLabelText("Scegli una password"), "password-lunga-123");
    await user.type(screen.getByLabelText("Ripeti la password"), "password-lunga-123");
    await user.click(screen.getByRole("button", { name: "Attiva account" }));

    expect(await screen.findByText(/Token di invito mancante/)).toBeInTheDocument();
    expect(chiamate).toBe(0);
  });

  it("conta i caratteri come il backend: un'emoji vale uno, non due", async () => {
    const user = userEvent.setup();
    let chiamate = 0;
    server.use(
      http.post("/api/v1/invitations/accept", () => {
        chiamate += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    // Undici caratteri, dodici unità UTF-16: `.length` la faceva passare e il
    // backend (pydantic, code point) la rifiutava con un 422.
    const password = "abcdefghij\u{1F600}";
    expect(password.length).toBe(12);

    renderWithProviders(<AcceptInvitePage />);
    await user.type(screen.getByLabelText("Scegli una password"), password);
    await user.type(screen.getByLabelText("Ripeti la password"), password);
    expect(screen.getByLabelText("Scegli una password")).toHaveValue(password);
    await user.click(screen.getByRole("button", { name: "Attiva account" }));

    expect(await screen.findByText(/almeno 12 caratteri\./)).toBeInTheDocument();
    expect(chiamate).toBe(0);
  });

  it("un invito scaduto si dice in italiano, nel banner e nell'avviso", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/invitations/accept", () =>
        HttpResponse.json(
          { type: "/problems/unauthorized", title: "Unauthorized", status: 401, detail: "Invitation expired." },
          { status: 401, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    renderWithProviders(<AcceptInvitePage />);
    const password = "abcdefghijkl";
    await user.type(screen.getByLabelText("Scegli una password"), password);
    await user.type(screen.getByLabelText("Ripeti la password"), password);
    await user.click(screen.getByRole("button", { name: "Attiva account" }));

    expect(await screen.findAllByText(/Invito scaduto: chiedine uno nuovo\./)).toHaveLength(2);
    expect(screen.queryByText(/Invitation expired/)).toBeNull();
  });
});
