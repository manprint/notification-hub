import type { AuditEventOut } from "../api/types";

/** Etichette in italiano per le azioni registrate dal backend
 * (backend/app/services/audit.py). Un'azione sconosciuta — perche' il backend
 * ne ha aggiunta una — resta leggibile come codice grezzo invece di sparire. */
export const ACTION_LABELS: Record<string, string> = {
  "notification.marked_read": "Segnata come letta",
  "notification.marked_unread": "Segnata come da leggere",
  "notification.marked_verified": "Segnata come verificata",
  "notification.marked_unverified": "Verifica annullata",
  "notification.bulk_marked_read": "Segnate come lette in blocco",
  "notification.deleted": "Notifica eliminata",
  "auth.login": "Accesso",
  "auth.login_failed": "Accesso rifiutato",
  "auth.logout": "Uscita",
};

/** Azioni della sezione "Letture e verifiche": stesso elenco di
 * NOTIFICATION_STATUS_ACTIONS lato backend. */
export const NOTIFICATION_STATUS_ACTIONS = [
  "notification.marked_read",
  "notification.marked_unread",
  "notification.marked_verified",
  "notification.marked_unverified",
  "notification.bulk_marked_read",
];

/** Un'etichetta per ogni `resource_type` che il backend scrive: le chiavi di
 *  RESOURCE_SPECS in backend/app/services/audit.py, piu' "session" per login e
 *  logout (backend/app/api/v1/auth.py). La tendina dei filtri si costruisce da
 *  qui: una lista scritta a parte restava indietro a ogni risorsa aggiunta. */
export const RESOURCE_LABELS: Record<string, string> = {
  notification: "Notifica",
  receiver: "Receiver",
  group: "Gruppo",
  user: "Utente",
  invitation: "Invito",
  delivery_channel: "Canale",
  group_channel_binding: "Associazione canale-gruppo",
  receiver_channel_override: "Override canale",
  severity_rule: "Regola di severity",
  severity_preset: "Preset di regole",
  severity_preset_rule: "Regola di preset",
  receiver_severity_preset: "Preset applicato",
  user_group_membership: "Appartenenza a gruppo",
  tenant: "Impostazioni tenant",
  session: "Sessione",
};

/** I tipi di risorsa filtrabili, nello stesso ordine delle etichette. */
export const RESOURCE_TYPES: string[] = Object.keys(RESOURCE_LABELS);

/** Il verbo delle azioni generiche `<risorsa>.<tipo>` (backend/app/services/audit.py,
 *  un evento per ogni INSERT, UPDATE o DELETE). Il nome della risorsa viene dopo
 *  i due punti, così il genere non va concordato con il verbo. */
const KIND_LABELS: Record<string, string> = {
  created: "Creazione",
  updated: "Modifica",
  deleted: "Eliminazione",
};

export function actionLabel(action: string): string {
  const explicit = ACTION_LABELS[action];
  if (explicit) return explicit;
  const dot = action.lastIndexOf(".");
  if (dot > 0) {
    const resource = RESOURCE_LABELS[action.slice(0, dot)];
    const kind = KIND_LABELS[action.slice(dot + 1)];
    if (resource && kind) return `${kind}: ${resource}`;
  }
  // Un'azione che il backend non ha ancora descritto resta leggibile com'è.
  return action;
}

export function resourceLabel(resourceType: string): string {
  return RESOURCE_LABELS[resourceType] ?? resourceType;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "sì" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** "verified: no → sì": il diff dei soli campi cambiati, in una riga sola. */
export function describeChanges(event: AuditEventOut): string[] {
  if (!event.changes) return [];
  return Object.entries(event.changes).map(
    ([field, change]) => `${field}: ${formatValue(change.before)} → ${formatValue(change.after)}`,
  );
}

/** Quante notifiche ha toccato l'evento: 1, o il conteggio di un bulk-read. */
export function affectedCount(event: AuditEventOut): number {
  const count = event.context?.count;
  return typeof count === "number" ? count : 1;
}

/** Quanto testo di `resource_label` sta in una cella. Per una notifica e' una
 *  fotografia di `content_preview` (fino a 255 caratteri): intera, un log
 *  allarga la riga e spinge fuori vista le altre colonne. */
export const LABEL_MAX_CHARS = 80;

export function shortLabel(label: string, max = LABEL_MAX_CHARS): string {
  return label.length <= max ? label : `${label.slice(0, max).trimEnd()}…`;
}

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

function pad(value: number, width = 2): string {
  return String(value).padStart(width, "0");
}

/** L'istante in ISO 8601 con l'offset del fuso del browser
 *  ("2026-09-22T00:00:00.000+02:00"), non in UTC: chi legge la richiesta vede
 *  lo stesso giorno che ha scelto. */
function toLocalIso(date: Date): string {
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `.${pad(date.getMilliseconds(), 3)}${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  );
}

function dayBoundary(day: string | null | undefined, end: boolean): string | undefined {
  const match = day ? DAY.exec(day) : null;
  if (!match) return undefined;
  const [, year, month, date] = match.map(Number);
  // Costruita coi campi locali: il cambio dell'ora legale lo gestisce Date.
  const instant = end
    ? new Date(year, month - 1, date, 23, 59, 59, 999)
    : new Date(year, month - 1, date, 0, 0, 0, 0);
  return toLocalIso(instant);
}

/** Il giorno di un `<input type="date">` ("YYYY-MM-DD") come inizio del giorno
 *  nel fuso del browser. Mandato nudo, il backend lo legge come mezzanotte nel
 *  fuso del server. */
export function startOfDay(day: string | null | undefined): string | undefined {
  return dayBoundary(day, false);
}

/** Come sopra, ma la fine del giorno (23:59:59.999 locali): il backend confronta
 *  `occurred_at <= to`, e con il giorno nudo "A = oggi" escludeva tutto oggi. */
export function endOfDay(day: string | null | undefined): string | undefined {
  return dayBoundary(day, true);
}
