import { apiGetFile } from "../api/client";
import { useAction } from "../hooks/useAction";
import type { AuditFilters } from "../hooks/useAuditEvents";
import ErrorBanner from "./ErrorBanner";

/** Esporta esattamente cio' che i filtri a schermo selezionano: l'export che
 * scarica "tutto" costringerebbe a filtrare di nuovo nel foglio di calcolo. */
export default function AuditExportButton({
  filters,
  notificationStatusOnly = false,
}: {
  filters: AuditFilters;
  notificationStatusOnly?: boolean;
}) {
  const { busy, error, run } = useAction();

  async function download() {
    await run(async () => {
      const query = new URLSearchParams({ format: "csv" });
      if (notificationStatusOnly) query.set("notification_status_only", "true");
      for (const [key, value] of Object.entries(filters)) {
        if (value) query.set(key, String(value));
      }
      const { content, filename } = await apiGetFile(
        `/api/v1/audit/export?${query.toString()}`,
        "audit.csv",
      );
      const url = URL.createObjectURL(new Blob([content], { type: "text/csv" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    });
  }

  return (
    <>
      <button type="button" onClick={() => void download()} disabled={busy !== null}>
        {busy !== null ? "Esporto…" : "Esporta CSV"}
      </button>
      {error && <ErrorBanner error={error} />}
    </>
  );
}
