import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense, lazy } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "../ErrorBoundary";

function Esplode(): never {
  throw new Error("rendering rotto");
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // React registra l'errore in console: in questi test è atteso.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("un errore di rendering mostra un ripiego in italiano con il pulsante per ricaricare", () => {
    render(
      <ErrorBoundary>
        <Esplode />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Questa pagina non si è caricata");
    expect(screen.getByRole("button", { name: "Ricarica la pagina" })).toBeInTheDocument();
  });

  it("al cambio di pagina (resetKey) torna a mostrare i figli", () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="/consegne">
        <Esplode />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();

    rerender(
      <ErrorBoundary resetKey="/gruppi">
        <p>Gruppi</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Gruppi")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("un chunk di pagina mancante ricarica una volta sola e lo ricorda", async () => {
    sessionStorage.clear();
    const reload = vi.fn();
    const Pagina = lazy(() =>
      Promise.reject(
        new TypeError("Failed to fetch dynamically imported module: /assets/Pagina-1.js"),
      ),
    );
    render(
      <ErrorBoundary reload={reload}>
        <Suspense fallback={<p>attesa</p>}>
          <Pagina />
        </Suspense>
      </ErrorBoundary>,
    );

    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(sessionStorage.getItem("notifyhub.chunk_reload")).not.toBeNull();
  });

  it("un chunk mancante dopo un ricaricamento già fatto mostra il ripiego, senza ricaricare", async () => {
    sessionStorage.setItem("notifyhub.chunk_reload", "1");
    const reload = vi.fn();
    const Pagina = lazy(() =>
      Promise.reject(
        new TypeError("Failed to fetch dynamically imported module: /assets/Pagina-1.js"),
      ),
    );
    render(
      <ErrorBoundary reload={reload}>
        <Suspense fallback={<p>attesa</p>}>
          <Pagina />
        </Suspense>
      </ErrorBoundary>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Questa pagina non si è caricata");
    expect(reload).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Ricarica la pagina" }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("un errore che non è un chunk non ricarica da solo", () => {
    sessionStorage.clear();
    const reload = vi.fn();
    render(
      <ErrorBoundary reload={reload}>
        <Esplode />
      </ErrorBoundary>,
    );
    expect(reload).not.toHaveBeenCalled();
  });

  it("senza errori mostra i figli come sono", () => {
    render(
      <ErrorBoundary>
        <p>tutto bene</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("tutto bene")).toBeInTheDocument();
  });
});
