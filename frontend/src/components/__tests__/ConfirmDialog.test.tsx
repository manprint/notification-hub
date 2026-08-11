import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ConfirmDialog from "../ConfirmDialog";

describe("ConfirmDialog", () => {
  it("T-UI4 test_confirm_richiede_testo_esatto: si abilita solo con corrispondenza esatta", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        title="Elimina gruppo"
        expectedText="Server Produzione"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    const confirmButton = screen.getByRole("button", { name: "Conferma" });
    const input = screen.getByLabelText(/digita/i);

    expect(confirmButton).toBeDisabled();

    await user.type(input, "Server");
    expect(confirmButton).toBeDisabled();

    await user.clear(input);
    await user.type(input, "server produzione");
    expect(confirmButton).toBeDisabled();

    await user.clear(input);
    await user.type(input, "Server Produzione");
    expect(confirmButton).toBeEnabled();

    await user.click(confirmButton);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("e' modale, prende il focus e si chiude con Escape", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        title="Elimina"
        expectedText="conferma"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    const dialog = screen.getByRole("dialog", { name: "Elimina" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByLabelText(/digita/i)).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
