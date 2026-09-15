import { Link, useSearchParams } from "react-router-dom";
import type { AuditEventOut } from "../api/types";
import AuditExportButton from "../components/AuditExportButton";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import SettingsTabs from "../components/SettingsTabs";
import { type AuditFilters, useAuditEvents } from "../hooks/useAuditEvents";
import { NOTIFICATION_STATUS_ACTIONS, actionLabel, affectedCount } from "../lib/audit";
import { formatDateTime } from "../lib/format";

/** Vista dedicata a "segna come letta" e "segna come verificata": la stessa
 * tabella dell'audit, filtrata sulle azioni che rispondono alla domanda
 * ricorrente — chi ha gestito questa notifica. */
export default function AuditNotificationStatusPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: AuditFilters = {
    notification_id: searchParams.get("notification_id") ?? undefined,
    action: searchParams.get("action") ?? undefined,
    from: searchParams.get("from") ?? undefined,
    to: searchParams.get("to") ?? undefined,
  };

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useAuditEvents("/api/v1/audit/notification-status", filters);

  const rows = data?.pages.flatMap((page) => page.events) ?? [];

  function setParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  }

  const columns: DataTableColumn<AuditEventOut>[] = [
    {
      key: "occurred_at",
      header: "Quando",
      render: (event) => formatDateTime(event.occurred_at),
    },
    {
      key: "actor",
      header: "Chi",
      render: (event) => (
        <div className="cell-preview">
          {event.actor_email}
          <div className="cell-diagnostics">
            {event.actor_role}
            {event.ip ? ` · ${event.ip}` : ""}
          </div>
        </div>
      ),
    },
    { key: "action", header: "Azione", render: (event) => actionLabel(event.action) },
    {
      key: "notification",
      header: "Notifica",
      render: (event) => {
        if (event.action === "notification.bulk_marked_read") {
          return (
            <div className="cell-preview">
              <span>{`${affectedCount(event)} notifiche`}</span>
              <div className="cell-diagnostics">operazione in blocco</div>
            </div>
          );
        }
        if (!event.resource_id) return "—";
        return (
          <div className="cell-preview">
            <Link to={`/notifications/${event.resource_id}`}>
              {event.resource_label || "(vuota)"}
            </Link>
          </div>
        );
      },
    },
  ];

  const attivi = Object.values(filters).filter(Boolean).length;

  return (
    <div>
      <div className="page-header">
        <h1>Letture e verifiche</h1>
      </div>
      <SettingsTabs />
      <p className="page-subtitle">
        Lo storico completo dei passaggi, ripristini compresi: lo stato attuale lo dice già la
        notifica, qui c'è chi l'ha cambiato e quando.
      </p>
      {error && <ErrorBanner error={error} />}

      <div className="card">
        <div className="filters">
          <div className="form-row grow">
            <label htmlFor="audit-notification-id">ID notifica</label>
            <input
              id="audit-notification-id"
              type="text"
              placeholder="incolla l'id di una notifica"
              value={filters.notification_id ?? ""}
              onChange={(event) => setParam("notification_id", event.target.value)}
            />
          </div>
          <div className="form-row">
            <label htmlFor="audit-action">Azione</label>
            <select
              id="audit-action"
              value={filters.action ?? ""}
              onChange={(event) => setParam("action", event.target.value)}
            >
              <option value="">Tutte</option>
              {NOTIFICATION_STATUS_ACTIONS.map((action) => (
                <option key={action} value={action}>
                  {actionLabel(action)}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label htmlFor="audit-status-from">Da</label>
            <input
              id="audit-status-from"
              type="date"
              value={filters.from ?? ""}
              onChange={(event) => setParam("from", event.target.value)}
            />
          </div>
          <div className="form-row">
            <label htmlFor="audit-status-to">A</label>
            <input
              id="audit-status-to"
              type="date"
              value={filters.to ?? ""}
              onChange={(event) => setParam("to", event.target.value)}
            />
          </div>
          <div className="filters-actions">
            {attivi > 0 && (
              <button onClick={() => setSearchParams(new URLSearchParams())}>
                Azzera i filtri ({attivi})
              </button>
            )}
            <AuditExportButton filters={filters} notificationStatusOnly />
          </div>
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(event) => event.id}
        loading={isLoading}
        emptyMessage="Nessuna lettura o verifica con questi filtri."
        hasMore={hasNextPage}
        onLoadMore={() => void fetchNextPage()}
        loadingMore={isFetchingNextPage}
      />
    </div>
  );
}
