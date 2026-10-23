// Testi in italiano per le risposte d'errore del backend (RFC 9457, `detail`).
// Il backend scrive il `detail` in inglese: l'interfaccia è in italiano, quindi
// i messaggi noti si traducono qui, in un solo posto. Tutto il resto ricade su
// una frase generica che porta con sé il dettaglio originale, così il errore
// resta leggibile anche quando il backend ne aggiunge uno nuovo.

import type { ApiError } from "../api/types";

/** Il `detail` così come lo scrive il backend (backend/app/api, main.py) → italiano. */
const KNOWN_DETAILS: Record<string, string> = {
  "Invalid credentials.": "Email o password non corrette.",
  "Too many login attempts. Please try again later.":
    "Troppi tentativi di accesso: riprova tra qualche minuto.",
  "Public registration is disabled. Use the bootstrap CLI.":
    "La registrazione pubblica è disabilitata: chiedi a un proprietario di invitarti.",
  "Email already registered.": "Esiste già un utente con questa email.",
  "Invitation not found.": "Invito non trovato.",
  "Invitation already accepted.": "Questo invito è già stato accettato.",
  "Invitation expired.": "Invito scaduto: chiedine uno nuovo.",
  "Invalid or already accepted invitation.":
    "Invito non valido o già accettato: chiedine uno nuovo.",
  "Invalid refresh token.": "Sessione non valida: accedi di nuovo.",
  "Refresh token revoked or invalid.": "Sessione non valida: accedi di nuovo.",
  "Refresh token expired.": "Sessione scaduta: accedi di nuovo.",
  "Invalid authorization header.": "Sessione non valida: accedi di nuovo.",
  "Invalid or expired token.": "Sessione scaduta: accedi di nuovo.",
  "User or tenant inactive.": "Utente o organizzazione disattivati: contatta un amministratore.",
  "Insufficient permissions.": "Non hai i permessi per questa operazione.",
  "Viewers have read-only access.": "Con il ruolo «Sola lettura» non puoi modificare nulla.",
  "Not a member of this receiver group.": "Non fai parte del gruppo di questo receiver.",
  "Only an owner can grant the owner role.":
    "Solo un proprietario può assegnare il ruolo di proprietario.",
  "Only an owner can modify an owner.": "Solo un proprietario può modificare un proprietario.",
  "Cannot remove or demote the last owner of the tenant.":
    "Non si può rimuovere o declassare l'ultimo proprietario.",
  "Group not found.": "Gruppo non trovato.",
  "Receiver not found.": "Receiver non trovato.",
  "User not found.": "Utente non trovato.",
  "Notification not found.": "Notifica non trovata.",
  "Delivery channel not found.": "Canale non trovato.",
  "Delivery not found.": "Consegna non trovata.",
  "Binding not found.": "Collegamento non trovato.",
  "Override not found.": "Override non trovato.",
  "Severity preset not found.": "Preset di severity non trovato.",
  "Preset rule not found.": "Regola del preset non trovata.",
  "Severity rule not found.": "Regola di severity non trovata.",
  "Only a dead delivery can be retried.": "Si può ri-accodare solo una consegna morta.",
  "Daily notification quota exceeded for this tenant.": "Quota giornaliera di notifiche superata.",
  "Storage quota exceeded for this tenant.": "Quota di archiviazione superata.",
  "Request validation failed.": "Alcuni campi non sono validi.",
  "The request conflicts with the current state of the data.":
    "La richiesta è in conflitto con i dati attuali: ricarica la pagina.",
  "An internal error occurred.": "Errore interno del server: riprova tra poco.",
  "The filters select more than 50000 events. Narrow the date range and retry.":
    "Il filtro seleziona più di 50.000 eventi: restringi l'intervallo di date e riprova.",
  "Invalid cursor.": "Paginazione non valida: ricarica l'elenco.",
  "Rate limit exceeded for source IP.": "Troppe richieste: riprova tra poco.",
  "Rate limit exceeded for this receiver.": "Troppe richieste per questo receiver: riprova tra poco.",
  "Object storage unreachable.": "Archivio dei contenuti non raggiungibile: riprova più tardi.",
  "confirm must match the exact group name.":
    "Il nome digitato non corrisponde a quello del gruppo.",
};

/** La frase generica per tipo di problema, quando il `detail` non è tra quelli noti. */
const TYPE_MESSAGES: Record<string, string> = {
  "/problems/validation-error": "Alcuni campi non sono validi.",
  "/problems/not-found": "Elemento non trovato.",
  "/problems/conflict": "Operazione in conflitto con i dati attuali.",
  "/problems/unauthorized": "Sessione non valida: accedi di nuovo.",
  "/problems/forbidden": "Operazione non consentita con il tuo ruolo.",
  "/problems/rate-limited": "Troppe richieste: riprova tra poco.",
  "/problems/payload-too-large": "Il contenuto è troppo grande.",
  "/problems/unsupported-media-type": "Formato non supportato.",
  "/problems/quota-exceeded": "Quota superata.",
  "/problems/last-owner": "Non si può rimuovere l'ultimo proprietario.",
  "/problems/storage-unavailable": "Archivio non raggiungibile: riprova più tardi.",
  "/problems/internal-error": "Errore interno del server: riprova tra poco.",
};

const GENERIC_MESSAGE = "Operazione non riuscita.";

/** Il testo di un errore spezzato in due: la frase in italiano, e il `detail`
 *  originale quando non è tra quelli tradotti (resta leggibile, ma a parte). */
export interface ProblemText {
  message: string;
  detail: string;
}

export function problemText(error: ApiError): ProblemText {
  // L'errore di rete nasce già in italiano nel client.
  if (error.type === "/problems/network-unreachable" && error.detail) {
    return { message: error.detail, detail: "" };
  }

  const detail = error.detail?.trim() ?? "";
  if (detail === "") {
    // Una pagina d'errore del proxy (502, 504, 413) non ha un detail: lo stato
    // HTTP è l'unica cosa che dice cos'è successo, e resta nel messaggio.
    const typed = TYPE_MESSAGES[error.type];
    if (typed) return { message: typed, detail: "" };
    const status = error.status > 0 ? ` (HTTP ${error.status})` : "";
    return { message: `${GENERIC_MESSAGE}${status}`, detail: "" };
  }
  const known = KNOWN_DETAILS[detail];
  if (known) return { message: known, detail: "" };
  return { message: TYPE_MESSAGES[error.type] ?? GENERIC_MESSAGE, detail };
}

/** Il messaggio in una riga sola, per il toast. */
export function problemMessage(error: ApiError): string {
  const { message, detail } = problemText(error);
  return detail === "" ? message : `${message} ${detail}`;
}

const PYDANTIC_PATTERNS: Array<[RegExp, (...groups: string[]) => string]> = [
  [/^Field required$/, () => "Campo obbligatorio."],
  [
    /^Input should be less than or equal to (.+)$/,
    (max) => `Il valore deve essere al massimo ${max}.`,
  ],
  [
    /^Input should be greater than or equal to (.+)$/,
    (min) => `Il valore deve essere almeno ${min}.`,
  ],
  [/^Input should be a valid integer/, () => "Inserisci un numero intero."],
  [/^Input should be a valid number/, () => "Inserisci un numero."],
  [/^Input should be a valid boolean/, () => "Scegli sì o no."],
  [/^Input should be a valid URL/, () => "Inserisci un URL valido."],
  [/^Input should be a valid string/, () => "Inserisci un testo."],
  [
    /^String should have at least (\d+) characters?$/,
    (n) => `Il testo deve avere almeno ${n} caratteri.`,
  ],
  [
    /^String should have at most (\d+) characters?$/,
    (n) => `Il testo può avere al massimo ${n} caratteri.`,
  ],
];

/** Un messaggio di validazione di pydantic (`extra.errors[].msg`) in italiano.
 *  Quello che non si riconosce resta com'è: meglio un testo inglese che nessun testo. */
export function validationMessage(msg: string): string {
  for (const [pattern, text] of PYDANTIC_PATTERNS) {
    const match = pattern.exec(msg);
    if (match) return text(...match.slice(1));
  }
  return msg;
}
