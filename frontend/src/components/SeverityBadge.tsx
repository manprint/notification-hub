import type { Severity } from "../api/types";

const LABELS: Record<Severity, string> = {
  critical: "Critica",
  error: "Errore",
  warning: "Attenzione",
  info: "Info",
  debug: "Debug",
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`severity-badge severity-${severity}`}>{LABELS[severity]}</span>;
}
