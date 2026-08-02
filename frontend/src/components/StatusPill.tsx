import type { DeliveryStatus, NotificationStatus } from "../api/types";

const LABELS: Record<NotificationStatus | DeliveryStatus, string> = {
  unread: "Non letta",
  read: "Letta",
  pending: "In attesa",
  sending: "In invio",
  sent: "Inviata",
  failed: "Fallita",
  dead: "Morta",
};

export default function StatusPill({ status }: { status: NotificationStatus | DeliveryStatus }) {
  return <span className="status-pill">{LABELS[status]}</span>;
}
