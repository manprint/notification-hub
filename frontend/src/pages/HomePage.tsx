import { useQuery } from "@tanstack/react-query";
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

  if (isLoading) return <EmptyState message="Caricamento…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return null;

  return (
    <div>
      <h1>Riepilogo</h1>

      <div className="card">
        <strong>{data.total_unread}</strong> notifiche non lette in totale
      </div>

      <div className="card">
        <h3>Per severity</h3>
        <div className="toolbar">
          {SEVERITIES.map((severity) => (
            <div key={severity}>
              <SeverityBadge severity={severity} /> {data.by_severity[severity] ?? 0}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Per gruppo</h3>
        <table>
          <thead>
            <tr>
              <th>Gruppo</th>
              <th>Totale</th>
              <th>Non lette</th>
            </tr>
          </thead>
          <tbody>
            {data.by_group.map((group) => (
              <tr key={group.group_id}>
                <td>{group.group_name}</td>
                <td>{group.total}</td>
                <td>{group.unread_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <p>{data.notifications_last_24h} notifiche ricevute nelle ultime 24 ore.</p>
        <p>
          <Link to="/deliveries?status=dead">{data.deliveries_dead} consegne in stato morto</Link>
        </p>
      </div>
    </div>
  );
}
