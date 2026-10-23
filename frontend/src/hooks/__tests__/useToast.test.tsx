import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "../useToast";

function Bottoni() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.success("Salvato")}>ok</button>
      <button onClick={() => toast.error("Non salvato")}>ko</button>
    </>
  );
}

function renderToasts() {
  render(
    <ToastProvider>
      <Bottoni />
    </ToastProvider>,
  );
}

describe("useToast", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("un errore è annunciato come alert e non sparisce da solo", () => {
    vi.useFakeTimers();
    renderToasts();

    fireEvent.click(screen.getByRole("button", { name: "ko" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Non salvato");

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getByText("Non salvato")).toBeInTheDocument();
  });

  it("un esito positivo è uno status e sparisce dopo cinque secondi", () => {
    vi.useFakeTimers();
    renderToasts();

    fireEvent.click(screen.getByRole("button", { name: "ok" }));
    expect(screen.getByText("Salvato").closest(".toast")).toHaveAttribute("role", "status");

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Salvato")).toBeNull();
  });
});
