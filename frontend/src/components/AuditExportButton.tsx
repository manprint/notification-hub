import { apiGetFile } from "../api/client";
import { useAction } from "../hooks/useAction";
import type { AuditFilters } from "../hooks/useAuditEvents";
import { UTF8_BOM, saveBlob } from "../lib/download";
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
      // Il backend manda UTF-8 senza BOM (e se un giorno lo mandasse,
      // response.text() lo toglie decodificando): lo si rimette qui, se no
      // Excel apre il file con la codifica di sistema e rovina gli accenti.
      saveBlob(new Blob([UTF8_BOM, content], { type: "text/csv;charset=utf-8" }), filename);
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
