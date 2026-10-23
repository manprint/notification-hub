import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ErrorBanner from "../ErrorBanner";
import type { ApiError } from "../../api/types";

// Forma reale di un 422 del backend (app/main.py -> validation_error_handler):
// `errors` arriva in `extra` perche' il client ci mette tutto quello che non e'
// type/title/detail/status.
const errore422: ApiError = {
  status: 422,
  type: "/problems/validation-error",
  title: "Validation Error",
  detail: "Request validation failed.",
  extra: {
    errors: [
      {
        type: "less_than_equal",
        loc: ["body", "rate_limit_per_min"],
        msg: "Input should be less than or equal to 2147483647",
        input: 99999999999,
        ctx: { le: 2147483647 },
      },
      {
        type: "missing",
        loc: ["body", "channel", "name"],
        msg: "Field required",
        input: {},
      },
    ],
  },
};

describe("ErrorBanner", () => {
  it("T-ERR1 mostra campo e motivo di ogni errore di validazione", () => {
    render(<ErrorBanner error={errore422} />);

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("Alcuni campi non sono validi.");
    const voci = within(banner).getAllByRole("listitem");
    expect(voci).toHaveLength(2);
    // "body" dice solo dove stava il campo: si mostra il nome del campo, e il
    // motivo di pydantic è in italiano.
    expect(voci[0]).toHaveTextContent(
      "rate_limit_per_min: Il valore deve essere al massimo 2147483647.",
    );
    expect(voci[1]).toHaveTextContent("channel.name: Campo obbligatorio.");
  });

  it("T-ERR4 traduce in italiano i messaggi noti del backend, non l'inglese", () => {
    render(
      <ErrorBanner
        error={{
          status: 401,
          type: "/problems/unauthorized",
          title: "Unauthorized",
          detail: "Invalid credentials.",
          extra: {},
        }}
      />,
    );

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("Email o password non corrette.");
    expect(banner).not.toHaveTextContent("Invalid credentials");
  });

  it("T-ERR5 un dettaglio non tradotto resta visibile, dopo una frase in italiano", () => {
    render(
      <ErrorBanner
        error={{ status: 500, type: "/problems/internal-error", title: "Internal", detail: "Disco pieno.", extra: {} }}
      />,
    );

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("Errore interno del server: riprova tra poco.");
    expect(within(banner).getByText("Disco pieno.")).toBeInTheDocument();
  });

  it("T-ERR2 senza dettagli mostra solo il messaggio", () => {
    render(
      <ErrorBanner
        error={{ status: 409, type: "/problems/conflict", title: "Conflict", detail: "Nome gia' usato.", extra: {} }}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Nome gia' usato.");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("T-ERR3 ignora voci malformate senza rompersi", () => {
    render(
      <ErrorBanner
        error={{
          ...errore422,
          extra: { errors: [null, "testo", { loc: "x" }, { loc: [], msg: "Corpo non valido" }] },
        }}
      />,
    );

    const voci = screen.getAllByRole("listitem");
    expect(voci).toHaveLength(1);
    expect(voci[0]).toHaveTextContent("Corpo non valido");
  });
});
