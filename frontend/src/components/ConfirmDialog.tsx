import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

interface ConfirmDialogProps {
  title: string;
  expectedText: string;
  children?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
}

export default function ConfirmDialog({
  title,
  expectedText,
  children,
  onConfirm,
  onCancel,
  confirmLabel = "Conferma",
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState("");
  const matches = typed === expectedText;
  const inputRef = useRef<HTMLInputElement>(null);
  const cancelRef = useRef(onCancel);
  const titleId = useId();
  cancelRef.current = onCancel;

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
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
        <div className="toolbar">
          <button type="button" onClick={onCancel}>
            Annulla
          </button>
          <button type="button" className="primary" disabled={!matches} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
