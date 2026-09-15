import type { DeliveryStatus, NotificationStatus } from "../api/types";

type Status = NotificationStatus | DeliveryStatus;

const LABELS: Record<Status, string> = {
  unread: "Non letta",
  read: "Letta",
  pending: "In attesa",
  sending: "In invio",
  sent: "Inviata",
  failed: "Fallita",
  dead: "Morta",
};

/** Il tono porta l'esito senza costringere a leggere la parola: in un elenco
 *  di consegne "Morta" e "Inviata" devono distinguersi da lontano. Il colore
 *  non è mai l'unico segnale — l'etichetta resta scritta. */
const TONES: Record<Status, string> = {
  unread: "info",
  read: "",
  pending: "",
  sending: "info",
  sent: "ok",
  failed: "warn",
  dead: "danger",
};

export default function StatusPill({ status }: { status: Status }) {
  const tone = TONES[status];
  return <span className={tone ? `status-pill ${tone}` : "status-pill"}>{LABELS[status]}</span>;
}
