import { useEffect, useId, useRef, type ReactNode } from "react";
import { useDialogKeyboard } from "../hooks/useDialogKeyboard";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Un salvataggio è in volo: il modulo non si chiude (×, Escape, sfondo)
   *  finché non finisce, altrimenti il suo esito e l'errore sparirebbero. */
  busy?: boolean;
}

/** Finestra per un modulo che interrompe la lettura della pagina (modifica di
 *  una riga): stessa cornice del dialogo di conferma, senza l'azione decisa
 *  dentro. Prima questi moduli comparivano in fondo alla pagina, lontano dalla
 *  riga su cui si era appena premuto "Modifica". */
export default function Modal({ title, onClose, children, busy = false }: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const requestClose = () => {
    if (!busy) onClose();
  };
  useDialogKeyboard(dialogRef, requestClose);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    // Il primo campo, non la × che nel DOM viene prima: chi apre "Modifica"
    // vuole scrivere, e partire dalla chiusura costringe a un Tab a vuoto.
    const dialog = dialogRef.current;
    const target =
      dialog?.querySelector<HTMLElement>("input, select, textarea") ??
      dialog?.querySelector<HTMLElement>("button");
    target?.focus();
    return () => previouslyFocused?.focus();
  }, []);

  return (
    <div
      className="confirm-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      {/* tabIndex -1: un click su un testo del dialogo lascia il fuoco sul
          dialogo invece di mandarlo sul body, fuori dalla finestra. */}
      <div
        ref={dialogRef}
        className="card confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="card-header">
          <h2 id={titleId}>{title}</h2>
          <button
            type="button"
            className="ghost"
            aria-label="Chiudi"
            disabled={busy}
            onClick={requestClose}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
