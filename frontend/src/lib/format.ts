/** Formattazioni condivise. Stavano scritte a mano in ogni pagina, con il
 *  risultato che la stessa data si leggeva in tre modi diversi in tre
 *  schermate. */

import type { UserRole, UserStatus } from "../api/types";

const LOCALE = "it-IT";

/** Data e ora complete: il formato di riferimento per gli elenchi. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(LOCALE);
}

/** Solo il giorno: scadenze e filtri, dove l'ora non aggiunge niente. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(LOCALE);
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString(LOCALE);
}

/** Come sopra, ma per i campi che hanno un significato quando sono vuoti
 *  ("non è mai arrivato niente"), non un trattino generico. */
export function formatInstantOr(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  return formatDateTime(value);
}

const BYTE_UNITS = ["byte", "kB", "MB", "GB"];

/** Dimensioni leggibili: 1048576 non dice niente, 1 MB sì. Il valore esatto
 *  resta disponibile nel title di chi lo mostra. */
export function formatBytes(value: number): string {
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < BYTE_UNITS.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? amount : Math.round(amount * 10) / 10;
  return `${rounded.toLocaleString(LOCALE)} ${BYTE_UNITS[unit]}`;
}

export const ROLE_LABELS: Record<UserRole, string> = {
  owner: "Proprietario",
  admin: "Amministratore",
  member: "Operatore",
  viewer: "Sola lettura",
};

export function roleLabel(role: UserRole): string {
  return ROLE_LABELS[role] ?? role;
}

const USER_STATUS_LABELS: Record<string, string> = {
  active: "Attiva",
  invited: "Invitata",
  disabled: "Disattivata",
};

export function userStatusLabel(status: UserStatus | string): string {
  return USER_STATUS_LABELS[status] ?? status;
}

export function channelTypeLabel(type: string): string {
  return type === "google_chat" ? "Google Chat" : type === "slack" ? "Slack" : type;
}
