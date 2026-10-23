import type { ApiError } from "../api/types";
import { problemText, validationMessage } from "../lib/problemMessages";

/** Un errore di validazione come lo scrive il backend in `extra.errors` di un
 *  422 (RequestValidationError di FastAPI, reso serializzabile da
 *  app/core/errors.py): `loc` e' il percorso del campo, `msg` il perche'. */
interface ValidationIssue {
  field: string;
  message: string;
}

/** Il primo elemento di `loc` dice solo dove stava il campo nella richiesta
 *  (corpo, query, percorso): per chi legge conta il nome del campo. */
const LOCATION_PREFIXES = new Set(["body", "query", "path", "header", "cookie"]);

function validationIssues(error: ApiError): ValidationIssue[] {
  const raw = error.extra?.errors;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item): ValidationIssue[] => {
    if (typeof item !== "object" || item === null) return [];
    const { loc, msg } = item as { loc?: unknown; msg?: unknown };
    if (typeof msg !== "string" || msg === "") return [];
    const parts = Array.isArray(loc) ? loc.map(String) : [];
    const path = parts.length > 1 && LOCATION_PREFIXES.has(parts[0]) ? parts.slice(1) : parts;
    return [{ field: path.join("."), message: validationMessage(msg) }];
  });
}

export default function ErrorBanner({ error, message }: { error: ApiError; message?: string }) {
  // Senza i dettagli un 422 diceva solo "Request validation failed.": vero, ma
  // non dice quale campo correggere.
  const issues = validationIssues(error);
  // `message` è per le pagine che sanno dire di più del backend (il backend usa
  // la stessa frase per gruppi, receiver e canali): in quel caso il testo della
  // pagina sostituisce quello generato, detail compreso.
  const text = message === undefined ? problemText(error) : { message, detail: "" };
  return (
    <div className="error-banner" role="alert" aria-live="assertive">
      {text.message}
      {text.detail && <span className="error-detail"> {text.detail}</span>}
      {issues.length > 0 && (
        <ul className="error-details">
          {issues.map((issue, index) => (
            <li key={`${issue.field}-${index}`}>
              {issue.field ? (
                <>
                  <code>{issue.field}</code>: {issue.message}
                </>
              ) : (
                issue.message
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
