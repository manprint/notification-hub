import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

interface ConfirmDialogProps {
  title: string;
  /** Testo da ribattere per sbloccare la conferma. Si usa per le operazioni
   *  che cancellano dati a cascata; per le altre (una regola, un invito) basta
   *  la conferma esplicita e il campo non compare. */
  expectedText?: string;
  children?: ReactNode;
  onConfirm: () => void;
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
  const matches = expectedText === undefined || typed === expectedText;
  const inputRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef(onCancel);
  const titleId = useId();
  cancelRef.current = onCancel;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    // Senza campo da ribattere il fuoco va sulla conferma: è l'unico controllo
    // che l'utente deve raggiungere, e da tastiera evita un Tab a vuoto.
    if (inputRef.current) inputRef.current.focus();
    else confirmRef.current?.focus();
    return () => previouslyFocused?.focus();
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelRef.current();
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
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        className="card confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={handleKeyDown}
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
          <button type="button" onClick={onCancel}>
            Annulla
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={destructive ? "primary danger" : "primary"}
            disabled={!matches}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
