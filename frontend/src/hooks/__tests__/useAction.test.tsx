// Il giro che fa ogni scrittura: "in corso", esito, errore. Senza questo, la
// differenza fra "salvato" e "non è successo niente" non si vede da nessuna
// parte dell'interfaccia.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ApiError } from "../../api/types";
import SaveIndicator from "../../components/SaveIndicator";
import { useAction } from "../useAction";
import { ToastProvider } from "../useToast";

function Provetta({ azione }: { azione: () => Promise<unknown> }) {
  const { busy, error, saveState, run } = useAction();
  return (
    <div>
      <button onClick={() => void run(azione, { name: "salva", success: "Fatto." })}>
        {busy === "salva" ? "In corso…" : "Salva"}
      </button>
      <SaveIndicator state={saveState} />
      {error && <p className="error-banner">{error.detail}</p>}
    </div>
  );
}

function renderProvetta(azione: () => Promise<unknown>) {
  return render(
    <ToastProvider>
      <Provetta azione={azione} />
    </ToastProvider>,
  );
}

describe("useAction", () => {
  it("a operazione riuscita mostra l'avviso e l'indicatore «Salvato»", async () => {
    const user = userEvent.setup();
    renderProvetta(() => Promise.resolve());

    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Due riscontri con ruoli diversi: l'avviso in basso (che passa) e
    // l'indicatore accanto al controllo (che resta il tempo di vederlo).
    expect(await screen.findByText("Fatto.")).toBeInTheDocument();
    expect(screen.getByText(/Salvato/)).toBeInTheDocument();
  });

  it("a operazione fallita l'errore resta in linea oltre all'avviso", async () => {
    const user = userEvent.setup();
    const guasto: ApiError = {
      status: 409,
      type: "/problems/conflict",
      title: "Conflict",
      detail: "Esiste già un receiver con questo nome.",
      extra: {},
    };
    renderProvetta(() => Promise.reject(guasto));

    await user.click(screen.getByRole("button", { name: "Salva" }));

    // L'avviso sparisce da solo dopo qualche secondo: il dettaglio deve
    // restare scritto accanto al modulo, non solo passare.
    await waitFor(() =>
      expect(screen.getAllByText(/Esiste già un receiver/).length).toBeGreaterThanOrEqual(2),
    );
    expect(screen.getByText(/Non salvato/)).toBeInTheDocument();
  });

  it("l'avviso si può chiudere a mano", async () => {
    const user = userEvent.setup();
    renderProvetta(() => Promise.resolve());

    await user.click(screen.getByRole("button", { name: "Salva" }));
    await screen.findByText("Fatto.");

    await user.click(screen.getByRole("button", { name: "Chiudi l'avviso" }));
    expect(screen.queryByText("Fatto.")).not.toBeInTheDocument();
  });

  it("l'errore precedente sparisce al tentativo successivo riuscito", async () => {
    const user = userEvent.setup();
    let fallisci = true;
    const guasto: ApiError = {
      status: 500,
      type: "/problems/internal-error",
      title: "Errore",
      detail: "Il server non ce l'ha fatta.",
      extra: {},
    };
    renderProvetta(() => (fallisci ? Promise.reject(guasto) : Promise.resolve()));

    await user.click(screen.getByRole("button", { name: "Salva" }));
    await screen.findAllByText(/Il server non ce l'ha fatta/);

    fallisci = false;
    await user.click(screen.getByRole("button", { name: "Salva" }));

    // Il banner del tentativo fallito non deve restare accanto a un salvataggio
    // riuscito: resterebbe un errore che non descrive più niente. L'avviso di
    // prima invece scade da sé, non viene ritirato.
    await waitFor(() => expect(screen.getByText(/Salvato/)).toBeInTheDocument());
    expect(document.querySelector(".error-banner")).toBeNull();
  });
});
