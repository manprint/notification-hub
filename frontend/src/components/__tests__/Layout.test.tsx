import { waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import Layout from "../Layout";
import { fixtureMe } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "../../pages/__tests__/testUtils";

const EMAIL_LUNGA = "fabio.pierri.amministrazione@synclab-consulting.example";

describe("Layout", () => {
  beforeEach(() => {
    localStorage.clear();
    // Una sessione salvata: il profilo arriva da /auth/me.
    localStorage.setItem("notifyhub.refresh_token", "refresh-salvato");
  });

  it("l'indirizzo della sessione sta intero nel title e va a capo solo fra le sue parti", async () => {
    server.use(http.get("/api/v1/auth/me", () => HttpResponse.json({ ...fixtureMe, email: EMAIL_LUNGA })));
    renderWithProviders(<Layout />);

    await waitFor(() => expect(document.querySelector(".app-brand-user")).not.toBeNull());
    const utente = document.querySelector(".app-brand-user") as HTMLElement;
    expect(utente).toHaveAttribute("title", `${EMAIL_LUNGA} · ACME`);
    // Il testo visibile non cambia: il <wbr> dopo ogni punto e @ non aggiunge caratteri.
    expect(utente).toHaveTextContent(`${EMAIL_LUNGA} · ACME`);
    expect(utente.querySelectorAll("wbr")).toHaveLength(4);
  });
});
