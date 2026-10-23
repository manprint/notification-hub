import { focusManager } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import HomePage from "../HomePage";
import { fixtureStatsSummary } from "../../api/mocks/handlers";
import { server } from "../../api/mocks/server";
import { renderWithProviders } from "./testUtils";

/** Il valore di una card KPI, per etichetta: lo stesso numero puo' comparire
 *  anche nella tabella dei gruppi. */
function kpi(etichetta: string): HTMLElement {
  return screen.getByText(etichetta, { selector: ".kpi-label" }).closest(".kpi") as HTMLElement;
}

describe("HomePage", () => {
  it("T-UI6 test_home_mostra_conteggi: mostra i conteggi e cinque severity", async () => {
    renderWithProviders(<HomePage />);

    // Il riepilogo del mock ora e' coerente (le non lette sono tutte del gruppo
    // g1): lo stesso numero sta nella card e nella riga del gruppo, quindi lo
    // si cerca dentro la card.
    await waitFor(() => {
      expect(
        within(kpi("Non lette")).getByText(String(fixtureStatsSummary.total_unread)),
      ).toBeInTheDocument();
    });

    // Cinque severity sempre, anche quelle che il backend omette perche' a
    // zero (by_severity non ha la chiave debug).
    expect(document.querySelectorAll(".severity-badge")).toHaveLength(5);
    expect(fixtureStatsSummary.by_severity.debug).toBeUndefined();
    const debug = screen.getByText("Debug").closest(".severity-count") as HTMLElement;
    expect(within(debug).getByText("0")).toBeInTheDocument();
  });

  it("un polling fallito lascia a video i dati precedenti, col banner sopra", async () => {
    let rotto = false;
    server.use(
      http.get("/api/v1/stats/summary", () =>
        rotto
          ? HttpResponse.json(
              {
                type: "/problems/internal-error",
                title: "Internal Server Error",
                status: 500,
                detail: "Riepilogo non disponibile",
              },
              { status: 500 },
            )
          : HttpResponse.json(fixtureStatsSummary),
      ),
    );
    renderWithProviders(<HomePage />);
    await waitFor(() => expect(within(kpi("Non lette")).getByText("5")).toBeInTheDocument());

    // Il giro successivo del polling fallisce. Il ritorno del focus rilancia
    // la query senza aspettare i 30 secondi.
    rotto = true;
    try {
      act(() => {
        focusManager.setFocused(false);
        focusManager.setFocused(true);
      });

      expect(await screen.findByRole("alert")).toHaveTextContent("Riepilogo non disponibile");
      // Un solo errore non cancella quello che si stava guardando.
      expect(within(kpi("Non lette")).getByText("5")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Server Produzione" })).toBeInTheDocument();
      expect(screen.getByText(/ultimo aggiornamento riuscito/)).toBeInTheDocument();
    } finally {
      focusManager.setFocused(undefined);
    }
  });

  it("senza dati precedenti l'errore occupa la pagina", async () => {
    server.use(
      http.get("/api/v1/stats/summary", () =>
        HttpResponse.json(
          { type: "/problems/internal-error", title: "Internal Server Error", status: 500, detail: "Riepilogo non disponibile" },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<HomePage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Riepilogo non disponibile");
    expect(screen.queryByText("Non lette", { selector: ".kpi-label" })).not.toBeInTheDocument();
  });

  it("T-UI22 test_riepilogo_espande_i_receiver: i receiver del gruppo compaiono solo da aperti", async () => {
    renderWithProviders(<HomePage />);
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Server Produzione" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "Backup notturno" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /mostra i receiver di server produzione/i }));

    const receiver = await screen.findByRole("link", { name: "Backup notturno" });
    // Riga cliccabile: porta alle notifiche del gruppo gia' filtrate su quel receiver.
    expect(receiver).toHaveAttribute("href", "/notifications?group_id=g1&receiver_id=r1");
    // Un receiver che non ha mai scritto resta in elenco, marcato come disabilitato.
    expect(screen.getByRole("link", { name: "Job mai partito" })).toBeInTheDocument();
    expect(screen.getByText("disabilitato")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /nascondi i receiver di server produzione/i }));
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Backup notturno" })).not.toBeInTheDocument();
    });
  });

  it("T-UI23 test_gruppo_senza_receiver_non_ha_toggle: niente freccia su un gruppo vuoto", async () => {
    renderWithProviders(<HomePage />);

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Backup" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /receiver di backup/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Backup" })).toHaveAttribute(
      "href",
      "/notifications?group_id=g2",
    );
  });

  it("le colonne di conteggio sono numeriche: intestazione e cella allineate a destra", async () => {
    renderWithProviders(<HomePage />);

    await screen.findByRole("link", { name: "Backup" });
    for (const nome of ["Totale", "Non lette"]) {
      expect(screen.getByRole("columnheader", { name: nome })).toHaveClass("num");
    }
    const riga = screen.getByRole("link", { name: "Backup" }).closest("tr") as HTMLElement;
    expect(riga.querySelectorAll("td.num")).toHaveLength(2);
  });

  it("il titolo Riepilogo c'e' anche mentre carica", () => {
    server.use(http.get("/api/v1/stats/summary", () => new Promise(() => {})));
    renderWithProviders(<HomePage />);

    expect(screen.getByRole("heading", { name: "Riepilogo" })).toBeInTheDocument();
    expect(screen.getByText("Caricamento…")).toBeInTheDocument();
  });

  it("il titolo Riepilogo c'e' anche quando non c'e' nessun dato e la richiesta fallisce", async () => {
    server.use(
      http.get("/api/v1/stats/summary", () =>
        HttpResponse.json(
          { type: "/problems/internal-error", title: "Internal Server Error", status: 500, detail: "Riepilogo non disponibile" },
          { status: 500 },
        ),
      ),
    );
    renderWithProviders(<HomePage />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Riepilogo non disponibile"));
    expect(screen.getByRole("heading", { name: "Riepilogo" })).toBeInTheDocument();
  });

});
