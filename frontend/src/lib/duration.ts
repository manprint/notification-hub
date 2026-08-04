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
