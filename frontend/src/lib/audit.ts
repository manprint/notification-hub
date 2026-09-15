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

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
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
