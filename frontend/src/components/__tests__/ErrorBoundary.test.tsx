import { render, screen } from "@testing-library/react";
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

  it("senza errori mostra i figli come sono", () => {
    render(
      <ErrorBoundary>
        <p>tutto bene</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("tutto bene")).toBeInTheDocument();
  });
});
