import type { Severity } from "../api/types";
import { severityLabel } from "../lib/format";

export default function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`severity-badge severity-${severity}`}>{severityLabel(severity)}</span>;
}
