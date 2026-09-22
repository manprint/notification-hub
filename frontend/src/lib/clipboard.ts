/** Copia un testo negli appunti; rifiuta se non ci riesce in nessun modo.
 *
 *  `navigator.clipboard` esiste solo in un contesto sicuro: su un'istanza
 *  servita in HTTP (una LAN senza certificato) è `undefined`, e chiamarlo
 *  sollevava un TypeError che nessuno raccoglieva — il pulsante non faceva
 *  niente e non diceva niente. Lì si ricade sul vecchio `execCommand("copy")`,
 *  che funziona anche fuori da HTTPS. */
export async function copyText(value: string): Promise<void> {
  const clipboard = (navigator as { clipboard?: Clipboard }).clipboard;
  if (clipboard && typeof clipboard.writeText === "function") {
    try {
      await clipboard.writeText(value);
      return;
    } catch {
      // permesso negato o documento senza fuoco: si prova il ripiego.
    }
  }
  if (!copyWithTextarea(value)) {
    throw new Error("Copia negli appunti non riuscita.");
  }
}

/** Ripiego per i contesti non sicuri: il testo va selezionato in un campo
 *  temporaneo, perché `execCommand("copy")` copia la selezione corrente. */
function copyWithTextarea(value: string): boolean {
  const previouslyFocused = document.activeElement as HTMLElement | null;
  const textarea = document.createElement("textarea");
  textarea.value = value;
  // readonly: niente tastiera virtuale sui telefoni. Fuori vista, ma non
  // display:none, che renderebbe il campo non selezionabile.
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "0";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  try {
    textarea.focus();
    textarea.select();
    return typeof document.execCommand === "function" && document.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
    previouslyFocused?.focus();
  }
}
