// Espressioni cron dell'attesa di un receiver: le stesse regole del backend
// (app/services/surveillance.py -> validate_cron), valutate qui solo per
// guidare l'operatore nel form. Il backend resta l'unica autorita': questa
// libreria non salva nulla, mostra e blocca.

import { parseExpression } from "cron-parser";

/** Minuto ora giorno mese giorno-settimana, come in crontab. */
export const CRON_FIELDS = 5;
/** Oltre non si va: stessa soglia di app/services/surveillance.py. */
export const CRON_MAX_CHARS = 100;

const MESSAGGIO_5_CAMPI =
  "L'espressione cron deve avere 5 campi come in crontab: minuto ora giorno mese giorno-settimana.";

/** Verifica un'espressione cron a 5 campi. Ritorna il messaggio d'errore, o
 *  null se accettabile. Specchia le regole di validate_cron del backend. */
export function validateCronExpression(expression: string): string | null {
  const candidate = expression.trim();
  if (candidate === "") return "L'espressione cron è vuota.";
  if (candidate.length > CRON_MAX_CHARS)
    return `L'espressione cron supera ${CRON_MAX_CHARS} caratteri.`;
  if (candidate.split(/\s+/).length !== CRON_FIELDS) return MESSAGGIO_5_CAMPI;
  try {
    const iter = parseExpression(candidate, { currentDate: new Date() });
    iter.next();
    return null;
  } catch {
    // Un'espressione che il parser non digerisce (range fuori, giorni
    // impossibili, testo libero) non e' salvabile: la si rifiuta qui.
    return `Espressione cron non valida: ${candidate}`;
  }
}

/** Verifica un nome di fuso orario IANA: vuoto o sconosciuto al runtime non
 *  passa. */
export function validateTimezone(name: string): string | null {
  const candidate = name.trim();
  if (candidate === "") return "Scegli un fuso orario correttamente.";
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: candidate });
    return null;
  } catch {
    return `Fuso orario non valido: ${candidate}`;
  }
}

/** Prossime occorrenze di un'espressione cron nel fuso dichiarato. Ritorna
 *  fino a `count` date (default 3). Una cron valida ma che non scatta mai
 *  (come `0 0 30 2 *`) ritorna una lista piu' corta o vuota, mai un errore. */
export function nextCronExecutions(
  expression: string,
  timezone: string,
  now: Date = new Date(),
  count = 3,
): Date[] {
  let iter;
  try {
    iter = parseExpression(expression, {
      currentDate: now,
      tz: timezone,
    });
  } catch {
    return [];
  }
  const dates: Date[] = [];
  for (let i = 0; i < count; i += 1) {
    try {
      dates.push(iter.next().toDate());
    } catch {
      // Nessuna occorrenza successiva nel range: ci si ferma con quel che c'e'.
      break;
    }
  }
  return dates;
}

/** Rappresentazione compatta e localizzata di una data d'esecuzione, nel fuso
 *  indicato. */
export function formatExecutionPreview(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat("it-IT", {
    timeZone: timezone,
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
