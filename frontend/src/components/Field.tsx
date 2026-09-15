import type { ReactNode } from "react";

interface FieldProps {
  /** Id del controllo contenuto: lega etichetta, suggerimento ed errore. */
  id: string;
  label: string;
  /** Obbligatorio: asterisco sull'etichetta. Il controllo porta anche
   *  `required`, così il browser lo blocca prima della richiesta. */
  required?: boolean;
  /** Facoltativo dichiarato: si usa nei moduli in cui la maggior parte dei
   *  campi è obbligatoria e l'eccezione va detta. */
  optional?: boolean;
  hint?: ReactNode;
  error?: string | null;
  /** Campo che occupa tutta la riga dentro .form-grid. */
  wide?: boolean;
  children: ReactNode;
}

/** Una riga di modulo: etichetta con obbligatorio/facoltativo, controllo,
 *  suggerimento ed errore, sempre nello stesso ordine e con gli stessi id. */
export default function Field({
  id,
  label,
  required = false,
  optional = false,
  hint,
  error,
  wide = false,
  children,
}: FieldProps) {
  return (
    <div className={wide ? "form-row wide" : "form-row"}>
      {/* Asterisco e «(facoltativo)» li mette il CSS (.is-required::after,
          .is-optional::after): dentro l'etichetta finirebbero nel nome
          accessibile del campo, che diventerebbe "Email *". Chi usa uno screen
          reader sente comunque l'obbligatorietà da `required` sul controllo, e
          l'assenza di `required` è già di per sé «facoltativo». */}
      <label className={labelClass(required, optional)} htmlFor={id}>
        {label}
      </label>
      {children}
      {hint && (
        <span className="field-hint" id={`${id}-hint`}>
          {hint}
        </span>
      )}
      {error && (
        <span className="field-error" id={`${id}-error`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

function labelClass(required: boolean, optional: boolean): string | undefined {
  if (required) return "is-required";
  if (optional) return "is-optional";
  return undefined;
}

interface FieldAria {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

/** Attributi da mettere sul controllo dentro un <Field> con lo stesso id:
 *  collega suggerimento ed errore al campo per chi usa uno screen reader, e
 *  colora il bordo quando la validazione ha rifiutato il valore. */
export function fieldAria(
  id: string,
  options: { hint?: unknown; error?: string | null } = {},
): FieldAria {
  const describedBy = [options.hint ? `${id}-hint` : null, options.error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  return {
    id,
    "aria-describedby": describedBy || undefined,
    "aria-invalid": options.error ? true : undefined,
  };
}

/** Legenda da mettere una volta sopra un modulo che ha campi obbligatori. */
export function RequiredLegend() {
  return (
    <p className="form-legend">
      I campi con <span className="required-mark">*</span> sono obbligatori.
    </p>
  );
}
