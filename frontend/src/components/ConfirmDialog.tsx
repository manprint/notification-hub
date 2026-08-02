import { useState, type ReactNode } from "react";

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

  return (
    <div className="card" role="dialog" aria-label={title}>
      <h3>{title}</h3>
      {children}
      <div className="form-row">
        <label htmlFor="confirm-text">{`Digita "${expectedText}" per confermare`}</label>
        <input
          id="confirm-text"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
      </div>
      <div className="toolbar">
        <button onClick={onCancel}>Annulla</button>
        <button className="primary" disabled={!matches} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}
