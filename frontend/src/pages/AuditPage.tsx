import { useSearchParams } from "react-router-dom";
import type { AuditEventOut, AuditOutcome } from "../api/types";
import AuditExportButton from "../components/AuditExportButton";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import SettingsTabs from "../components/SettingsTabs";
import { type AuditFilters, useAuditEvents } from "../hooks/useAuditEvents";
import { actionLabel, describeChanges, resourceLabel } from "../lib/audit";

const RESOURCE_TYPES = [
  "notification",
  "receiver",
  "group",
  "user",
  "invitation",
  "delivery_channel",
  "severity_rule",
  "severity_preset",
  "user_group_membership",
  "tenant",
  "session",
];

export default function AuditPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: AuditFilters = {
    resource_type: searchParams.get("resource_type") ?? undefined,
    outcome: (searchParams.get("outcome") as AuditOutcome | null) ?? undefined,
    from: searchParams.get("from") ?? undefined,
    to: searchParams.get("to") ?? undefined,
  };

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useAuditEvents("/api/v1/audit/events", filters);

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
      render: (event) => new Date(event.occurred_at).toLocaleString("it-IT"),
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
    {
      key: "action",
      header: "Azione",
      render: (event) => (
        <div className="cell-preview">
          {actionLabel(event.action)}
          {event.outcome === "failure" && <div className="cell-diagnostics">rifiutata</div>}
        </div>
      ),
    },
    {
      key: "resource",
      header: "Risorsa",
      render: (event) => (
        <div className="cell-preview">
          {resourceLabel(event.resource_type)}
          <div className="cell-diagnostics">{event.resource_label ?? event.resource_id ?? "—"}</div>
        </div>
      ),
    },
    {
      key: "changes",
      header: "Cosa è cambiato",
      render: (event) => {
        const changes = describeChanges(event);
        if (changes.length === 0) return "—";
        return (
          <ul className="audit-changes">
            {changes.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        );
      },
    },
  ];

  return (
    <div>
      <h1>Audit</h1>
      <SettingsTabs />
      <p className="page-subtitle">
        Ogni modifica fatta da una persona, con chi l'ha fatta e cosa è cambiato. L'ingestion e i
        job automatici non compaiono: non hanno un attore umano.
      </p>
      {error && <ErrorBanner error={error} />}

      <div className="card toolbar">
        <div className="form-row">
          <label htmlFor="audit-resource-type">Tipo di risorsa</label>
          <select
            id="audit-resource-type"
            value={filters.resource_type ?? ""}
            onChange={(event) => setParam("resource_type", event.target.value)}
          >
            <option value="">Tutte</option>
            {RESOURCE_TYPES.map((type) => (
              <option key={type} value={type}>
                {resourceLabel(type)}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="audit-outcome">Esito</label>
          <select
            id="audit-outcome"
            value={filters.outcome ?? ""}
            onChange={(event) => setParam("outcome", event.target.value)}
          >
            <option value="">Tutti</option>
            <option value="success">Riuscita</option>
            <option value="failure">Rifiutata</option>
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="audit-from">Da</label>
          <input
            id="audit-from"
            type="date"
            value={filters.from ?? ""}
            onChange={(event) => setParam("from", event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="audit-to">A</label>
          <input
            id="audit-to"
            type="date"
            value={filters.to ?? ""}
            onChange={(event) => setParam("to", event.target.value)}
          />
        </div>
        <AuditExportButton filters={filters} />
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(event) => event.id}
        loading={isLoading}
        emptyMessage="Nessun evento con questi filtri."
        hasMore={hasNextPage}
        onLoadMore={() => void fetchNextPage()}
        loadingMore={isFetchingNextPage}
      />
    </div>
  );
}
