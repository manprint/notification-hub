// Il mattone dei moduli: etichetta con obbligatorio/facoltativo, suggerimento
// ed errore legati al campo. Se qui salta il collegamento aria, l'errore lo
// vede solo chi guarda lo schermo.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Field, { RequiredLegend, fieldAria } from "../Field";

describe("Field", () => {
  it("l'asterisco non entra nel nome accessibile del campo", () => {
    render(
      <Field id="nome" label="Nome" required>
        <input {...fieldAria("nome")} />
      </Field>,
    );

    // L'obbligatorietà si vede (classe su cui il CSS mette l'asterisco) ma
    // l'etichetta resta "Nome": con "Nome *" nel testo, chi usa uno screen
    // reader sentirebbe leggere l'asterisco a ogni campo.
    expect(screen.getByLabelText("Nome")).toBeInTheDocument();
    expect(screen.getByText("Nome")).toHaveClass("is-required");
  });

  it("i campi facoltativi sono marcati, senza sporcare l'etichetta", () => {
    render(
      <Field id="descrizione" label="Descrizione" optional>
        <input {...fieldAria("descrizione")} />
      </Field>,
    );

    expect(screen.getByLabelText("Descrizione")).toBeInTheDocument();
    expect(screen.getByText("Descrizione")).toHaveClass("is-optional");
  });

  it("suggerimento ed errore sono legati al campo e l'errore lo annuncia", () => {
    render(
      <Field
        id="cron"
        label="Espressione cron"
        hint="Cinque campi separati da spazio."
        error="L'espressione cron deve avere 5 campi."
      >
        <input {...fieldAria("cron", { hint: true, error: "qualcosa" })} />
      </Field>,
    );

    const campo = screen.getByLabelText("Espressione cron");
    expect(campo).toHaveAttribute("aria-describedby", "cron-hint cron-error");
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("5 campi");
  });

  it("senza errore il campo non è marcato come non valido", () => {
    render(
      <Field id="nome" label="Nome">
        <input {...fieldAria("nome")} />
      </Field>,
    );

    const campo = screen.getByLabelText("Nome");
    expect(campo).not.toHaveAttribute("aria-invalid");
    expect(campo).not.toHaveAttribute("aria-describedby");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("la legenda spiega il simbolo una volta per modulo", () => {
    render(<RequiredLegend />);
    expect(screen.getByText(/sono obbligatori/)).toBeInTheDocument();
  });
});
