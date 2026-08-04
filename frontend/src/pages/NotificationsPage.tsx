import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet, apiPatch, apiPost } from "../api/client";
import type {
  GroupOut,
  NotificationListItemOut,
  NotificationListOut,
  NotificationStatus,
  Severity,
  SeveritySource,
} from "../api/types";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";
import StatusPill from "../components/StatusPill";
import { useNotifications } from "../hooks/useNotifications";
import {
  SEVERITY_SOURCE_LABELS,
  isSurveillanceSource,
  phaseLabel,
  severitySourceLabel,
} from "../lib/severitySource";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];
// Origini filtrabili, nell'ordine della catena di severity. Le due della
// sorveglianza stanno in fondo e sono quelle che si cercano piu' spesso:
// "fammi vedere solo i job che non hanno inviato".
const SOURCES: SeveritySource[] = [
  "explicit",
  "exit_code",
  "duration",
  "rule",
  "preset_rule",
  "receiver_default",
  "missing",
  "recovered",
];

export default function NotificationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const queryClient = useQueryClient();

  const groupId = searchParams.get("group_id") ?? undefined;
  const severityMin = (searchParams.get("severity_min") as Severity | null) ?? undefined;
  const status = (searchParams.get("status") as NotificationStatus | null) ?? undefined;
  const source = (searchParams.get("source") as SeveritySource | null) ?? undefined;

  const { data: groups } = useQuery({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useNotifications({
      group_id: groupId,
      severity_min: severityMin,
      status,
      source,
      q: q || undefined,
    });

  const rows = data?.pages.flatMap((page: NotificationListOut) => page.notifications) ?? [];

  async function markRead(id: string) {
    await apiPatch(`/api/v1/notifications/${id}`, { status: "read" });
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  async function bulkRead() {
    await apiPost("/api/v1/notifications/bulk-read", {
      group_id: groupId,
      severity_min: severityMin,
      // Lo stesso filtro della lista: "segna tutte come lette" non deve toccare
      // cio' che il filtro sull'origine sta tenendo fuori dalla vista.
      source,
      q: q || undefined,
    });
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  const columns: DataTableColumn<NotificationListItemOut>[] = [
    { key: "severity", header: "Severity", render: (n) => <SeverityBadge severity={n.severity} /> },
    {
      key: "content",
      header: "Contenuto",
      render: (n) => (
        <Link to={`/notifications/${n.id}`}>
          {n.content_preview}
          {n.content_normalized && <span className="status-pill" style={{ marginLeft: 8 }}>contenuto normalizzato</span>}
          {n.storage_backend === "object" && (
            <span className="status-pill" style={{ marginLeft: 8 }}>{n.content_size} byte su object storage</span>
          )}
        </Link>
      ),
    },
    {
      key: "source",
      header: "Origine",
      render: (n) => (
        <>
          <span
            className="status-pill"
            title={
              isSurveillanceSource(n.severity_source)
                ? "Notifica scritta da NotifyHub: nessuno l'ha inviata"
                : `Severity decisa da: ${severitySourceLabel(n.severity_source)}`
            }
          >
            {severitySourceLabel(n.severity_source)}
          </span>
          {n.phase === "start" && (
            <span
              className="status-pill"
              style={{ marginLeft: 6 }}
              title="Ping di avvio: l'esito arriva a fine esecuzione"
            >
              {phaseLabel(n.phase)}
            </span>
          )}
        </>
      ),
    },
    { key: "status", header: "Stato", render: (n) => <StatusPill status={n.status} /> },
    { key: "received_at", header: "Ricevuta", render: (n) => new Date(n.received_at).toLocaleString("it-IT") },
    {
      key: "actions",
      header: "",
      render: (n) =>
        n.status === "unread" ? (
          <button onClick={() => void markRead(n.id)}>Segna come letta</button>
        ) : null,
    },
  ];

  return (
    <div>
      <h1>Notifiche</h1>
      {error && <ErrorBanner error={error} />}

      <div className="toolbar">
        <select
          value={groupId ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              if (value) next.set("group_id", value);
              else next.delete("group_id");
              return next;
            });
          }}
        >
          <option value="">Tutti i gruppi</option>
          {groups?.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>

        <select
          value={severityMin ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              if (value) next.set("severity_min", value);
              else next.delete("severity_min");
              return next;
            });
          }}
        >
          <option value="">Qualsiasi severity</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          aria-label="Origine della notifica"
          value={source ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              if (value) next.set("source", value);
              else next.delete("source");
              return next;
            });
          }}
        >
          <option value="">Qualsiasi origine</option>
          {SOURCES.map((item) => (
            <option key={item} value={item}>
              {SEVERITY_SOURCE_LABELS[item]}
            </option>
          ))}
        </select>

        <input
          placeholder="Cerca nel contenuto…"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />

        <button onClick={() => void bulkRead()}>Segna tutte come lette</button>
      </div>

      <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
        La ricerca esamina i primi 4096 caratteri del contenuto.
      </p>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(n) => n.id}
        loading={isLoading}
        hasMore={hasNextPage}
        loadingMore={isFetchingNextPage}
        onLoadMore={() => void fetchNextPage()}
        emptyMessage="Nessuna notifica trovata."
      />
    </div>
  );
}
