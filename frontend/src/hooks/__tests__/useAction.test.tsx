// Il giro che fa ogni scrittura: "in corso", esito, errore. Senza questo, la
// differenza fra "salvato" e "non è successo niente" non si vede da nessuna
// parte dell'interfaccia.

import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
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

  it("un errore che non è di NotifyHub resta leggibile: niente banner vuoto", async () => {
    const user = userEvent.setup();
    // Un TypeError (connessione caduta a metà corpo) non ha titolo: il banner
    // non deve restare una scatola rossa senza parole.
    renderProvetta(() => Promise.reject(new TypeError("network error")));

    await user.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(screen.getByText(/Non salvato/)).toBeInTheDocument());
    expect(screen.getByText("Operazione non riuscita.", { exact: false })).toBeInTheDocument();
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

  describe("più salvataggi", () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    function wrapper({ children }: { children: ReactNode }) {
      return <ToastProvider>{children}</ToastProvider>;
    }

    /** Un'azione che finisce quando lo decide il test. */
    function inSospeso() {
      let finisci: () => void = () => undefined;
      const promessa = new Promise<void>((resolve) => {
        finisci = resolve;
      });
      return { azione: () => promessa, finisci };
    }

    it("il ritorno a «idle» del salvataggio precedente non cancella quello nuovo", async () => {
      vi.useFakeTimers();
      const { result } = renderHook(() => useAction(), { wrapper });

      await act(async () => {
        await result.current.run(() => Promise.resolve());
      });
      expect(result.current.saveState).toBe("saved");

      // Secondo salvataggio entro i 2,5 secondi del primo.
      act(() => vi.advanceTimersByTime(2000));
      const secondo = inSospeso();
      let esito: Promise<boolean> = Promise.resolve(false);
      act(() => {
        esito = result.current.run(secondo.azione);
      });

      // Qui scadeva il timer del primo e l'indicatore diceva "idle" a metà.
      act(() => vi.advanceTimersByTime(1000));
      expect(result.current.saveState).toBe("saving");

      await act(async () => {
        secondo.finisci();
        await esito;
      });
      expect(result.current.saveState).toBe("saved");
      act(() => vi.advanceTimersByTime(2000));
      expect(result.current.saveState).toBe("saved");
      act(() => vi.advanceTimersByTime(600));
      expect(result.current.saveState).toBe("idle");
    });

    it("con due operazioni in corso, la prima che finisce non libera busy", async () => {
      const { result } = renderHook(() => useAction(), { wrapper });
      const prima = inSospeso();
      const seconda = inSospeso();
      let esiti: Promise<boolean>[] = [];

      act(() => {
        esiti = [
          result.current.run(prima.azione, { name: "prima" }),
          result.current.run(seconda.azione, { name: "seconda" }),
        ];
      });
      expect(result.current.busy).toBe("seconda");

      await act(async () => {
        prima.finisci();
        await esiti[0];
      });
      // Prima: busy tornava null e "Salvato" compariva mentre la seconda
      // scriveva ancora.
      expect(result.current.busy).toBe("seconda");
      expect(result.current.saveState).toBe("saving");

      await act(async () => {
        seconda.finisci();
        await esiti[1];
      });
      expect(result.current.busy).toBeNull();
      expect(result.current.saveState).toBe("saved");
    });

    it("se una delle operazioni concorrenti fallisce, l'esito finale è «non salvato»", async () => {
      const guasto: ApiError = {
        status: 500,
        type: "/problems/internal-error",
        title: "Errore",
        detail: "Guasto.",
        extra: {},
      };
      const { result } = renderHook(() => useAction(), { wrapper });
      const seconda = inSospeso();
      let esiti: Promise<boolean>[] = [];

      act(() => {
        esiti = [
          result.current.run(() => Promise.reject(guasto), { name: "prima" }),
          result.current.run(seconda.azione, { name: "seconda" }),
        ];
      });
      await act(async () => {
        await esiti[0];
      });
      expect(result.current.saveState).toBe("saving");

      await act(async () => {
        seconda.finisci();
        await esiti[1];
      });
      expect(result.current.saveState).toBe("failed");
      expect(result.current.error?.detail).toBe("Guasto.");
    });

    it("smontato il componente, il timer di ritorno a «idle» viene annullato", async () => {
      vi.useFakeTimers();
      const clearTimeout = vi.spyOn(window, "clearTimeout");
      const { result, unmount } = renderHook(() => useAction(), { wrapper });
      await act(async () => {
        await result.current.run(() => Promise.resolve());
      });
      clearTimeout.mockClear();

      unmount();

      expect(clearTimeout).toHaveBeenCalled();
      clearTimeout.mockRestore();
    });
  });
});
