import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useDialogKeyboard } from "../hooks/useDialogKeyboard";

interface ConfirmDialogProps {
  title: string;
  /** Testo da ribattere per sbloccare la conferma. Si usa per le operazioni
   *  che cancellano dati a cascata; per le altre (una regola, un invito) basta
   *  la conferma esplicita e il campo non compare. */
  expectedText?: string;
  children?: ReactNode;
  /** Se restituisce una promessa, il dialogo resta occupato finché non si
   *  risolve: i pulsanti si disabilitano e un secondo click non parte. */
  onConfirm: () => void | Promise<unknown>;
  onCancel: () => void;
  confirmLabel?: string;
  /** Conferma di un'azione che toglie qualcosa: pulsante rosso. */
  destructive?: boolean;
}

export default function ConfirmDialog({
  title,
  expectedText,
  children,
  onConfirm,
  onCancel,
  confirmLabel = "Conferma",
  destructive = true,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);
  // Il ref, non solo lo stato: un doppio click arriva prima che il pulsante
  // disabilitato sia sullo schermo, e mandava due DELETE.
  const pendingRef = useRef(false);
  const matches = expectedText === undefined || typed === expectedText;
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useDialogKeyboard(dialogRef, () => {
    // Annullare a metà non ferma la richiesta già partita: farebbe solo
    // sparire il dialogo prima di sapere com'è andata.
    if (!pendingRef.current) onCancel();
  });

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    // Senza campo da ribattere il fuoco va sulla conferma: è l'unico controllo
    // che l'utente deve raggiungere, e da tastiera evita un Tab a vuoto.
    if (inputRef.current) inputRef.current.focus();
    else confirmRef.current?.focus();
    return () => previouslyFocused?.focus();
  }, []);

  async function handleConfirm() {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    try {
      await onConfirm();
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  return (
    <div
      className="confirm-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pendingRef.current) onCancel();
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
        aria-busy={pending || undefined}
        tabIndex={-1}
      >
        <h2 id={titleId}>{title}</h2>
        {children}
        {expectedText !== undefined && (
          <div className="form-row">
            <label htmlFor="confirm-text">{`Digita "${expectedText}" per confermare`}</label>
            <input
              ref={inputRef}
              id="confirm-text"
              autoComplete="off"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
          </div>
        )}
        <div className="form-actions">
          <button type="button" disabled={pending} onClick={onCancel}>
            Annulla
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={destructive ? "primary danger" : "primary"}
            disabled={!matches || pending}
            onClick={() => void handleConfirm()}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
