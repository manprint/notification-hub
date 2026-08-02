import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPatch } from "../api/client";
import type { ApiError, NotificationDetailOut } from "../api/types";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";
import StatusPill from "../components/StatusPill";
import { useSession } from "../hooks/useSession";

const DELETE_ALLOWED_ROLES = ["owner", "admin", "member"];

export default function NotificationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { role } = useSession();

  const { data, isLoading, error } = useQuery<NotificationDetailOut, ApiError>({
    queryKey: ["notification", id],
    queryFn: () => apiGet<NotificationDetailOut>(`/api/v1/notifications/${id}`),
    enabled: Boolean(id),
  });

  if (isLoading) return <EmptyState message="Caricamento…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return null;

  async function markRead() {
    await apiPatch(`/api/v1/notifications/${id}`, { status: "read" });
    await queryClient.invalidateQueries({ queryKey: ["notification", id] });
  }

  async function remove() {
    await apiDelete(`/api/v1/notifications/${id}`);
    navigate("/notifications", { replace: true });
  }

  return (
    <div>
      <h1>Dettaglio notifica</h1>

      <div className="card">
        <SeverityBadge severity={data.severity} /> <StatusPill status={data.status} />
        <p>
          Origine severity: <strong>{data.severity_source}</strong>
          {data.severity_source === "rule" && data.matched_pattern && (
            <>
              {" "}
              — pattern vincente: <code>{data.matched_pattern}</code>
            </>
          )}
        </p>
        <p>Ricevuta: {new Date(data.received_at).toLocaleString("it-IT")}</p>
        {data.source_ip && <p>Sorgente: {data.source_ip}</p>}
      </div>

      <div className="card">
        <h3>Contenuto</h3>
        {data.content !== null ? (
          <pre style={{ whiteSpace: "pre-wrap" }}>{data.content}</pre>
        ) : (
          <div>
            <p>{`Contenuto salvato su object storage (${data.content_size} byte).`}</p>
            {data.content_url && (
              <a href={data.content_url} download>
                <button>Scarica contenuto completo</button>
              </a>
            )}
          </div>
        )}
      </div>

      <div className="toolbar">
        {data.status === "unread" && <button onClick={() => void markRead()}>Segna come letta</button>}
        {role !== null && DELETE_ALLOWED_ROLES.includes(role) && (
          <button onClick={() => void remove()}>Elimina</button>
        )}
      </div>
    </div>
  );
}
