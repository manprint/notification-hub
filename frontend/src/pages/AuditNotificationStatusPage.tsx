import { Link, useSearchParams } from "react-router-dom";
import type { AuditEventOut } from "../api/types";
import AuditExportButton from "../components/AuditExportButton";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import ResourceLocation from "../components/ResourceLocation";
import SettingsTabs from "../components/SettingsTabs";
import { type AuditFilters, useAuditEvents } from "../hooks/useAuditEvents";
import {
  NOTIFICATION_STATUS_ACTIONS,
  actionLabel,
  affectedCount,
  endOfDay,
  shortLabel,
  startOfDay,
} from "../lib/audit";
import { formatDate, formatTime } from "../lib/format";

/** Vista dedicata a "segna come letta" e "segna come verificata": la stessa
 * tabella dell'audit, filtrata sulle azioni che rispondono alla domanda
 * ricorrente — chi ha gestito questa notifica. */
export default function AuditNotificationStatusPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // Nell'URL il giorno scelto, all'API l'intervallo di quel giorno nel fuso di
  // chi guarda: vedi startOfDay/endOfDay.
  const fromDay = searchParams.get("from") ?? "";
  const toDay = searchParams.get("to") ?? "";

  const filters: AuditFilters = {
    notification_id: searchParams.get("notification_id") ?? undefined,
    action: searchParams.get("action") ?? undefined,
    from: startOfDay(fromDay),
    to: endOfDay(toDay),
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
      render: (event) => (
        <span className="received-at">
          <span>{formatDate(event.occurred_at)}</span>
          <span>{formatTime(event.occurred_at)}</span>
        </span>
      ),
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
      // `resource_label` e' la fotografia della notifica al momento del fatto
      // (spec 9.6, righe autosufficienti): resta leggibile anche quando la
      // notifica non c'e' piu'. Accorciata, perche' il corpo di un messaggio
      // non allarghi la tabella; il testo intero sta nel title. "Apri" solo se
      // la notifica esiste ancora: il backend risolve la posizione seguendo la
      // notifica (services/audit_location.py), e dopo la purge o
      // l'eliminazione receiver_id torna nullo. Un link a una notifica
      // cancellata porterebbe a un 404.
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
            <span title={event.resource_label ?? undefined}>
              {event.resource_label ? shortLabel(event.resource_label) : "(vuota)"}
            </span>
            <div className="cell-diagnostics">
              {event.receiver_id !== null ? (
                <Link to={`/notifications/${event.resource_id}`}>Apri</Link>
              ) : (
                "notifica non più presente"
              )}
            </div>
          </div>
        );
      },
    },
    {
      key: "location",
      header: "Gruppo / Receiver",
      render: (event) => <ResourceLocation event={event} />,
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

      {/* Il filtro su una notifica sola non si digita: ci si arriva dal suo
          dettaglio, con "Chi l'ha letta o verificata". Qui si vede che c'e' e
          si toglie, invece di restare un elenco corto senza spiegazione. */}
      {filters.notification_id && (
        <div className="card filter-notice">
          <span>Storico di una sola notifica.</span>
          <div className="row-actions">
            <Link to={`/notifications/${filters.notification_id}`}>Apri la notifica</Link>
            <button onClick={() => setParam("notification_id", "")}>Mostrale tutte</button>
          </div>
        </div>
      )}

      <div className="card">
        <div className="filters">
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
              value={fromDay}
              onChange={(event) => setParam("from", event.target.value)}
            />
          </div>
          <div className="form-row">
            <label htmlFor="audit-status-to">A</label>
            <input
              id="audit-status-to"
              type="date"
              value={toDay}
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
