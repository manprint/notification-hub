// Durate: stessa resa compatta del backend (app/outbound/formatters/duration.py)
// e del wrapper notifyhub-run.sh, cosi lo stesso job letto in dashboard, su
// Slack o nel log del cron mostra lo stesso numero scritto allo stesso modo.

export function formatDurationMs(ms: number): string {
  const total = Math.max(Math.trunc(ms), 0);
  const seconds = Math.floor(total / 1000);
  if (seconds < 60) {
    // Sotto il minuto i millisecondi contano: distinguono mezzo secondo di
    // lavoro da un comando morto subito.
    return `${seconds}.${String(total % 1000).padStart(3, "0")}s`;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return hours > 0 ? `${hours}h${pad(minutes)}m${pad(rest)}s` : `${minutes}m${pad(rest)}s`;
}

export function formatDurationSeconds(seconds: number): string {
  return formatDurationMs(seconds * 1000);
}

/** Intervalli dell'attesa di un receiver: stessa resa di `format_seconds` in
 *  app/services/surveillance.py, che e' quella scritta nelle notifiche di
 *  assenza. Diversa da formatDurationMs perche' qui la scala e il giorno ("ogni
 *  1g"), non il millisecondo. */
export function formatIntervalSeconds(seconds: number): string {
  const total = Math.max(Math.trunc(seconds), 0);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return `${minutes}m${String(total % 60).padStart(2, "0")}s`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h${String(minutes % 60).padStart(2, "0")}m`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days}g${String(restHours).padStart(2, "0")}h` : `${days}g`;
}

export type DurationUnit = "s" | "m" | "h" | "g";

export const DURATION_UNIT_LABELS: Record<DurationUnit, string> = {
  s: "secondi",
  m: "minuti",
  h: "ore",
  g: "giorni",
};

const UNIT_FACTOR: Record<DurationUnit, number> = { s: 1, m: 60, h: 3600, g: 86400 };

export function toSeconds(amount: number, unit: DurationUnit): number {
  return amount * UNIT_FACTOR[unit];
}

/** Il massimo che il backend accetta sui campi interi del receiver (rate limit,
 *  limite corpo, soglia di durata, intervallo e tolleranza dell'attesa): le
 *  colonne sono integer di PostgreSQL, e oltre questo valore l'API risponde 422. */
export const INT4_MAX = 2_147_483_647;

/** La quantita' piu' grande che si puo' scrivere in un'unita' senza superare
 *  INT4_MAX secondi: serve come `max` del campo. */
export function maxAmount(unit: DurationUnit): number {
  return Math.floor(INT4_MAX / UNIT_FACTOR[unit]);
}

export type ParsedNumber = { ok: true; value: number } | { ok: false; error: string };

const MESSAGGIO_VUOTO = "Campo obbligatorio: scrivi un numero.";
const MESSAGGIO_NON_NUMERO = "Non è un numero valido.";

/** Un campo intero del modulo (rate limit, limite corpo). Rifiuta con un
 *  messaggio il campo vuoto, i decimali, i valori non finiti (`1e308` compreso)
 *  e quelli fuori da [min, max]: meglio dirlo qui che ricevere un 422, o peggio
 *  salvare 0 perche' `Number("")` vale 0. */
export function parseIntegerInput(
  raw: string,
  { min, max = INT4_MAX, empty = MESSAGGIO_VUOTO }: { min: number; max?: number; empty?: string },
): ParsedNumber {
  const text = raw.trim();
  if (text === "") return { ok: false, error: empty };
  const value = Number(text);
  if (Number.isNaN(value)) return { ok: false, error: MESSAGGIO_NON_NUMERO };
  if (value > max) return { ok: false, error: `Troppo grande: il massimo è ${max}.` };
  if (!Number.isFinite(value)) return { ok: false, error: MESSAGGIO_NON_NUMERO };
  if (!Number.isInteger(value)) {
    return { ok: false, error: "Serve un numero intero, senza decimali." };
  }
  if (value < min) return { ok: false, error: `Il minimo è ${min}.` };
  return { ok: true, value };
}

/** Una durata scritta come quantita' + unita', convertita nei secondi interi che
 *  l'API vuole. I decimali vanno bene solo se il risultato e' un numero intero di
 *  secondi (1,5 ore si', mezzo secondo no); il tetto si controlla dopo la
 *  conversione, perche' 30000 giorni sono troppi anche se 30000 sta nel campo. */
export function parseDurationInput(
  raw: string,
  unit: DurationUnit,
  { minSeconds, empty = MESSAGGIO_VUOTO }: { minSeconds: number; empty?: string },
): ParsedNumber {
  const text = raw.trim();
  if (text === "") return { ok: false, error: empty };
  const amount = Number(text);
  if (Number.isNaN(amount)) return { ok: false, error: MESSAGGIO_NON_NUMERO };
  const exact = amount * UNIT_FACTOR[unit];
  if (exact > INT4_MAX) {
    return {
      ok: false,
      error: `Troppo grande: il massimo è ${maxAmount(unit)} ${DURATION_UNIT_LABELS[unit]} (${INT4_MAX} secondi).`,
    };
  }
  if (!Number.isFinite(exact)) return { ok: false, error: MESSAGGIO_NON_NUMERO };
  const seconds = Math.round(exact);
  // Tolleranza per l'aritmetica in virgola mobile: 0,7 minuti fanno 42 secondi
  // anche se 0.7 * 60 non e' esattamente 42 in binario.
  if (Math.abs(exact - seconds) > 1e-6) {
    return { ok: false, error: "Deve corrispondere a un numero intero di secondi." };
  }
  if (seconds < minSeconds) {
    return {
      ok: false,
      error:
        minSeconds === 0
          ? "Non può essere negativa."
          : `Il minimo è ${formatIntervalSeconds(minSeconds)}.`,
    };
  }
  return { ok: true, value: seconds };
}

/** Secondi -> coppia (quantita, unita) piu leggibile per un campo di modifica:
 *  600 diventa "10 minuti", non "600 secondi". L'unita di default sui campi
 *  vuoti e il minuto, che e la scala dei job messi in cron. */
export function splitDuration(seconds: number | null): { amount: string; unit: DurationUnit } {
  if (seconds === null) return { amount: "", unit: "m" };
  if (seconds % 86400 === 0) return { amount: String(seconds / 86400), unit: "g" };
  if (seconds % 3600 === 0) return { amount: String(seconds / 3600), unit: "h" };
  if (seconds % 60 === 0) return { amount: String(seconds / 60), unit: "m" };
  return { amount: String(seconds), unit: "s" };
}
