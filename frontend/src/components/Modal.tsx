import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

/** Finestra per un modulo che interrompe la lettura della pagina (modifica di
 *  una riga): stessa cornice del dialogo di conferma, senza l'azione decisa
 *  dentro. Prima questi moduli comparivano in fondo alla pagina, lontano dalla
 *  riga su cui si era appena premuto "Modifica". */
export default function Modal({ title, onClose, children }: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

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

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeRef.current();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
      ),
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="confirm-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="card confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={handleKeyDown}
      >
        <div className="card-header">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="ghost" aria-label="Chiudi" onClick={onClose}>
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
