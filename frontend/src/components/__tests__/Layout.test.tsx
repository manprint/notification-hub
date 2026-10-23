import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Layout from "../Layout";
import { fixtureMe } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "../../pages/__tests__/testUtils";

const EMAIL_LUNGA = "fabio.pierri.amministrazione@synclab-consulting.example";

/** Finge uno schermo: `fasciaRiga` dice se il media query del menu a riga
 *  (max-width: 1000px) corrisponde. La geometria: il menu occupa 400px da x=0,
 *  la voce attiva sta a x=500 ed è larga 80px. */
function simulaSchermo(fasciaRiga: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: fasciaRiga && query === "(max-width: 1000px)",
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const box =
      this.tagName === "NAV"
        ? { left: 0, width: 400 }
        : this.getAttribute("aria-current") === "page"
          ? { left: 500, width: 80 }
          : { left: 0, width: 0 };
    return { ...box, right: box.left + box.width, top: 0, bottom: 0, height: 0, x: box.left, y: 0 } as DOMRect;
  });
}

describe("Layout", () => {
  beforeEach(() => {
    localStorage.clear();
    // Una sessione salvata: il profilo arriva da /auth/me.
    localStorage.setItem("notifyhub.refresh_token", "refresh-salvato");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete (window as { matchMedia?: unknown }).matchMedia;
  });

  it("sotto i 1000px il menu a riga centra la voce attiva, anche a 900px", async () => {
    simulaSchermo(true);
    renderWithProviders(<Layout />, ["/notifications"]);

    const menu = await screen.findByRole("navigation", { name: "Navigazione principale" });
    await waitFor(() => expect(menu.querySelector('a[aria-current="page"]')).not.toBeNull());
    // Centro della voce (500 + 40) meno metà menu (200): 340.
    expect(menu.scrollLeft).toBe(340);
  });

  it("sopra i 1000px il menu non si sposta: è una colonna", async () => {
    simulaSchermo(false);
    renderWithProviders(<Layout />, ["/notifications"]);

    const menu = await screen.findByRole("navigation", { name: "Navigazione principale" });
    await waitFor(() => expect(menu.querySelector('a[aria-current="page"]')).not.toBeNull());
    expect(menu.scrollLeft).toBe(0);
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
