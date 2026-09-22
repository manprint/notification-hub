// La copia di slug, URL e link d'invito: su un'istanza servita in HTTP
// `navigator.clipboard` non esiste, e prima il pulsante falliva in silenzio.

import { afterEach, describe, expect, it, vi } from "vitest";
import { copyText } from "../clipboard";

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
const originalExecCommand = Object.getOwnPropertyDescriptor(document, "execCommand");

function setClipboard(value: unknown) {
  Object.defineProperty(navigator, "clipboard", { value, configurable: true });
}

function setExecCommand(value: unknown) {
  Object.defineProperty(document, "execCommand", { value, configurable: true });
}

afterEach(() => {
  if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
  else delete (navigator as { clipboard?: unknown }).clipboard;
  if (originalExecCommand) Object.defineProperty(document, "execCommand", originalExecCommand);
  else delete (document as { execCommand?: unknown }).execCommand;
});

describe("copyText", () => {
  it("usa la Clipboard API quando c'è", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard({ writeText });
    const execCommand = vi.fn(() => true);
    setExecCommand(execCommand);

    await copyText("slug-123");

    expect(writeText).toHaveBeenCalledWith("slug-123");
    expect(execCommand).not.toHaveBeenCalled();
  });

  it("senza Clipboard API (HTTP) ripiega su execCommand con un campo temporaneo", async () => {
    setClipboard(undefined);
    let selezionato = "";
    const execCommand = vi.fn(() => {
      // execCommand copia la selezione corrente: il valore deve essere lì,
      // selezionato per intero.
      const campo = document.querySelector("textarea");
      if (campo && campo.selectionStart === 0 && campo.selectionEnd === campo.value.length) {
        selezionato = campo.value;
      }
      return true;
    });
    setExecCommand(execCommand);

    await expect(copyText("https://notifyhub.lan/invite#token=abc")).resolves.toBeUndefined();

    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(selezionato).toBe("https://notifyhub.lan/invite#token=abc");
    // Il campo temporaneo non resta nella pagina.
    expect(document.querySelector("textarea")).toBeNull();
  });

  it("se la Clipboard API rifiuta (permesso negato) prova comunque il ripiego", async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new DOMException("negato")) });
    const execCommand = vi.fn(() => true);
    setExecCommand(execCommand);

    await copyText("valore");

    expect(execCommand).toHaveBeenCalledWith("copy");
  });

  it("se falliscono tutti e due, rifiuta invece di fingere un successo", async () => {
    setClipboard(undefined);
    setExecCommand(vi.fn(() => false));

    await expect(copyText("valore")).rejects.toThrow();
  });
});
