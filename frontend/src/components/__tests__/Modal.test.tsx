// La finestra che ospita i moduli di modifica: se il fuoco esce o Escape non
// chiude, da tastiera ci si resta dentro senza via d'uscita.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ConfirmDialog from "../ConfirmDialog";
import Modal from "../Modal";

function renderModal(onClose = vi.fn()) {
  const utils = render(
    <Modal title="Modifica gruppo" onClose={onClose}>
      <p>Il nome compare nell'elenco dei gruppi.</p>
      <label htmlFor="nome">Nome</label>
      <input id="nome" />
      <button type="button">Salva</button>
    </Modal>,
  );
  return { onClose, ...utils };
}

describe("Modal", () => {
  it("è un dialogo modale col titolo come nome accessibile", () => {
    renderModal();
    const dialog = screen.getByRole("dialog", { name: "Modifica gruppo" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("porta il fuoco sul primo campo, non lo lascia sul pulsante che l'ha aperta", () => {
    renderModal();
    expect(screen.getByLabelText("Nome")).toHaveFocus();
  });

  it("Escape chiude", async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("il click sullo sfondo chiude, quello dentro no", async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await user.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    // Lo sfondo è il contenitore del dialogo: cliccarlo è il gesto per
    // rinunciare senza cercare la ×.
    const backdrop = screen.getByRole("dialog").parentElement as HTMLElement;
    await user.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("la × chiude", async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await user.click(screen.getByRole("button", { name: "Chiudi" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("il Tab gira dentro la finestra invece di uscire sulla pagina", async () => {
    const user = userEvent.setup();
    renderModal();

    const campo = screen.getByLabelText("Nome");
    const salva = screen.getByRole("button", { name: "Salva" });
    const chiudi = screen.getByRole("button", { name: "Chiudi" });

    expect(campo).toHaveFocus();
    await user.tab();
    expect(chiudi === document.activeElement || salva === document.activeElement).toBe(true);

    // Dall'ultimo elemento si torna al primo, non al contenuto sotto.
    salva.focus();
    await user.tab();
    expect(chiudi).toHaveFocus();

    // E all'indietro dal primo si va all'ultimo.
    await user.tab({ shift: true });
    expect(salva).toHaveFocus();
  });

  it("dopo un click su un testo del dialogo Escape chiude ancora", async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal();

    // Un click su un testo non focalizzabile spostava il fuoco sul body, e il
    // listener sul dialogo da lì non riceveva più niente.
    await user.click(screen.getByText(/compare nell'elenco/));
    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("col fuoco finito fuori dal dialogo, il Tab lo riporta dentro", async () => {
    const user = userEvent.setup();
    render(
      <>
        <button type="button">Pulsante della pagina</button>
        <Modal title="Modifica gruppo" onClose={vi.fn()}>
          <input aria-label="Nome" />
        </Modal>
      </>,
    );

    (document.activeElement as HTMLElement | null)?.blur();
    expect(document.body).toHaveFocus();
    await user.tab();

    // Senza il listener sul documento il Tab andava al pulsante della pagina
    // sotto, fuori da una finestra modale.
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("con una conferma aperta sopra, Escape chiude solo la conferma", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onCancel = vi.fn();
    render(
      <Modal title="Modifica" onClose={onClose}>
        <input aria-label="Campo" />
        <ConfirmDialog title="Sicuro?" onConfirm={vi.fn()} onCancel={onCancel} />
      </Modal>,
    );

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });
});
