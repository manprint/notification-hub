import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../api/client";
import type { ApiError, Severity, StatsSummaryOut } from "../api/types";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];
const POLL_INTERVAL_MS = 30_000;

export default function HomePage() {
  const { data, isLoading, error } = useQuery<StatsSummaryOut, ApiError>({
    queryKey: ["stats-summary"],
    queryFn: () => apiGet<StatsSummaryOut>("/api/v1/stats/summary"),
    refetchInterval: POLL_INTERVAL_MS,
  });
  // Gruppi aperti: lo stato sta qui e non nell'URL perche' e' una preferenza di
  // lettura momentanea, non una vista da condividere. Il polling ogni 30s
  // riscrive i numeri ma non richiude quel che l'operatore ha aperto.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(groupId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  if (isLoading) return <EmptyState message="Caricamento…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return null;

  return (
    <div>
      <div className="page-header">
        <h1>Riepilogo</h1>
      </div>

      {/* I tre numeri che si guardano per primi, affiancati: in colonna
          occupavano tre schermate di card mezze vuote. */}
      <div className="kpi-grid">
        <div className="kpi">
          <span className="kpi-label">Non lette</span>
          <span className="kpi-value accent">{data.total_unread}</span>
          <span className="kpi-note">
            <Link to="/notifications">Vai alle notifiche</Link>
          </span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Ricevute nelle ultime 24 ore</span>
          <span className="kpi-value">{data.notifications_last_24h}</span>
          <span className="kpi-note">Su tutti i gruppi visibili</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Consegne morte</span>
          <span className={data.deliveries_dead > 0 ? "kpi-value danger" : "kpi-value"}>
            {data.deliveries_dead}
          </span>
          <span className="kpi-note">
            <Link to="/deliveries?status=dead">Tentativi esauriti, da ri-accodare</Link>
          </span>
        </div>
      </div>

      <div className="card">
        <h3>Per severity</h3>
        <div className="severity-counts">
          {SEVERITIES.map((severity) => (
            <span className="severity-count" key={severity}>
              <SeverityBadge severity={severity} />
              <strong>{data.by_severity[severity] ?? 0}</strong>
            </span>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Per gruppo / receiver</h3>
        <p className="card-hint">
          Apri un gruppo per vedere i totali dei singoli receiver. Un receiver a zero non ha mai
          ricevuto notifiche.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="stats-toggle-col"></th>
                <th>Gruppo / receiver</th>
                <th>Totale</th>
                <th>Non lette</th>
              </tr>
            </thead>
            <tbody>
              {data.by_group.map((group) => {
                const receivers = group.receivers ?? [];
                const open = expanded.has(group.group_id);
                return (
                  <Fragment key={group.group_id}>
                    <tr>
                      <td className="stats-toggle-col">
                        {receivers.length > 0 && (
                          <button
                            className="stats-toggle"
                            aria-expanded={open}
                            aria-label={
                              open
                                ? `Nascondi i receiver di ${group.group_name}`
                                : `Mostra i receiver di ${group.group_name}`
                            }
                            onClick={() => toggle(group.group_id)}
                          >
                            {open ? "▾" : "▸"}
                          </button>
                        )}
                      </td>
                      <td>
                        <Link to={`/notifications?group_id=${group.group_id}`}>
                          {group.group_name}
                        </Link>
                      </td>
                      <td>{group.total}</td>
                      <td>{group.unread_count}</td>
                    </tr>
                    {open &&
                      receivers.map((receiver) => (
                        <tr key={receiver.receiver_id} className="stats-receiver-row">
                          <td className="stats-toggle-col"></td>
                          <td>
                            <span className="status-cell">
                              <Link
                                to={`/notifications?group_id=${group.group_id}&receiver_id=${receiver.receiver_id}`}
                              >
                                {receiver.receiver_name}
                              </Link>
                              {receiver.status === "disabled" && (
                                <span className="status-pill warn">disabilitato</span>
                              )}
                            </span>
                          </td>
                          <td>{receiver.total}</td>
                          <td>{receiver.unread_count}</td>
                        </tr>
                      ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        {data.by_group.length === 0 && <EmptyState message="Nessun gruppo." />}
      </div>
    </div>
  );
}
