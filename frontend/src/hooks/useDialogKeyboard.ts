import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE =
  'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])';

/** Dialoghi aperti, in ordine di apertura: la tastiera la gestisce solo quello
 *  in cima. Con una conferma aperta sopra un modulo, Escape chiude la
 *  conferma, non tutti e due. */
const openDialogs: HTMLElement[] = [];

/** Il dialogo in cima: il più recente che non ne contiene un altro. Un dialogo
 *  annidato nel DOM di un altro si registra per primo (gli effetti dei figli
 *  partono prima di quelli del genitore), ma è lui a stare sopra. */
function topDialog(): HTMLElement | undefined {
  for (let i = openDialogs.length - 1; i >= 0; i -= 1) {
    const candidate = openDialogs[i];
    if (!openDialogs.some((other) => other !== candidate && candidate.contains(other))) {
      return candidate;
    }
  }
  return undefined;
}

/** Ordine del documento esplicito: il primo e l'ultimo del giro del Tab devono
 *  essere davvero i primi e gli ultimi nella pagina, senza fidarsi di come il
 *  motore restituisce una lista di selettori (jsdom 29 li raggruppa per selettore). */
function inOrdineDelDocumento(elementi: NodeListOf<HTMLElement>): HTMLElement[] {
  return Array.from(elementi).sort((a, b) =>
    a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1,
  );
}

/** Escape e giro del Tab dentro un dialogo modale.
 *
 *  Il listener sta sul documento, non sul dialogo: un click su un testo non
 *  focalizzabile dentro il dialogo manda il fuoco sul body, e un onKeyDown sul
 *  dialogo da lì non riceve più niente — né Escape né Tab, che finirebbe sulla
 *  pagina sotto. Se il fuoco è uscito, il Tab lo riporta dentro. */
export function useDialogKeyboard(
  dialogRef: RefObject<HTMLElement>,
  onEscape: () => void,
): void {
  const escapeRef = useRef(onEscape);
  useEffect(() => {
    escapeRef.current = onEscape;
  }, [onEscape]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    openDialogs.push(dialog);

    function handleKeyDown(event: KeyboardEvent) {
      if (!dialog || topDialog() !== dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        escapeRef.current();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = inOrdineDelDocumento(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const current = document.activeElement;
      if (!(current instanceof Node) || !dialog.contains(current) || current === dialog) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && current === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && current === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      const index = openDialogs.lastIndexOf(dialog);
      if (index !== -1) openDialogs.splice(index, 1);
    };
  }, [dialogRef]);
}
