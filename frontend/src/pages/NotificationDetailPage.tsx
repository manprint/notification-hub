import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPatch } from "../api/client";
import type { ApiError, NotificationDetailOut, NotificationStatus } from "../api/types";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";
import { isSurveillanceSource, phaseLabel, severitySourceLabel } from "../lib/severitySource";
import StatusPill from "../components/StatusPill";
import { useSession } from "../hooks/useSession";
import { formatDurationMs } from "../lib/duration";

const DELETE_ALLOWED_ROLES = ["owner", "admin", "member"];

export default function NotificationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { role } = useSession();
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery<NotificationDetailOut, ApiError>({
    queryKey: ["notification", id],
    queryFn: () => apiGet<NotificationDetailOut>(`/api/v1/notifications/${id}`),
    enabled: Boolean(id),
  });

  if (isLoading) return <EmptyState message="Caricamento…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return null;

  async function runAction(name: string, action: () => Promise<void>) {
    setActionError(null);
    setBusyAction(name);
    try {
      await action();
    } catch (err) {
      setActionError(err as ApiError);
    } finally {
      setBusyAction(null);
    }
  }

  async function setStatus(status: NotificationStatus) {
    await runAction("status", async () => {
      await apiPatch(`/api/v1/notifications/${id}`, { status });
      await queryClient.invalidateQueries({ queryKey: ["notification", id] });
    });
  }

  async function setVerified(verified: boolean) {
    await runAction("verified", async () => {
      await apiPatch(`/api/v1/notifications/${id}`, { verified });
      await queryClient.invalidateQueries({ queryKey: ["notification", id] });
    });
  }

  async function remove() {
    await runAction("delete", async () => {
      await apiDelete(`/api/v1/notifications/${id}`);
      navigate("/notifications", { replace: true });
    });
  }

  // L'endpoint del contenuto richiede il Bearer token: un <a href download>
  // partiva senza header Authorization e riceveva 401. Va scaricato dal client
  // API e consegnato al browser come blob.
  async function downloadContent() {
    await runAction("download", async () => {
      const text = await apiGet<string>(`/api/v1/notifications/${id}/content`);
      const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `notifica-${id}.txt`;
        anchor.click();
      } finally {
        URL.revokeObjectURL(url);
      }
    });
  }

  return (
    <div>
      <h1>Dettaglio notifica</h1>
      {actionError && <ErrorBanner error={actionError} />}

      <div className="card">
        <SeverityBadge severity={data.severity} /> <StatusPill status={data.status} />{" "}
        <span className={`status-pill${data.verified ? " verified" : ""}`}>
          {data.verified ? "Verificata" : "Non verificata"}
        </span>
        <p>
          Origine severity: <strong>{severitySourceLabel(data.severity_source)}</strong>
          {data.severity_source === "rule" && data.matched_pattern && (
            <>
              {" "}
              — pattern vincente: <code>{data.matched_pattern}</code>
            </>
          )}
        </p>
        {isSurveillanceSource(data.severity_source) && (
          <p className="card-hint">
            Notifica generata da NotifyHub, non inviata da nessuno: la sorveglianza dell'attesa del
            receiver si e' accorta che {data.severity_source === "missing" ? "un invio previsto non e' arrivato" : "gli invii sono ripresi dopo un'assenza"}.
          </p>
        )}
        {data.duration_ms !== null && (
          <p>
            Durata esecuzione: <strong>{formatDurationMs(data.duration_ms)}</strong>
          </p>
        )}
        {data.exit_code !== null && <p>Exit code: {data.exit_code}</p>}
        {data.phase !== null && (
          <p>
            Fase dell'esecuzione: <strong>{phaseLabel(data.phase)}</strong>
            {data.phase === "start" &&
              " — ping di avvio: dice che il job e' partito, non com'e' andato."}
          </p>
        )}
        <p>Ricevuta: {new Date(data.received_at).toLocaleString("it-IT")}</p>
        {data.source_ip && <p>Sorgente: {data.source_ip}</p>}
        {/* Chi ha gestito la notifica: la domanda ricorrente, a cui qui
            risponde il solo stato corrente. Lo storico dei passaggi (e dei
            ripristini) vive nell'audit, riservato a owner e admin. */}
        {data.read_by_email && (
          <p>
            Letta da <strong>{data.read_by_email}</strong>
            {data.read_at && ` il ${new Date(data.read_at).toLocaleString("it-IT")}`}
          </p>
        )}
        {data.verified_by_email && (
          <p>
            Verificata da <strong>{data.verified_by_email}</strong>
            {data.verified_at && ` il ${new Date(data.verified_at).toLocaleString("it-IT")}`}
          </p>
        )}
      </div>

      <div className="card">
        <h3>Contenuto</h3>
        {data.content !== null ? (
          <pre style={{ whiteSpace: "pre-wrap" }}>{data.content}</pre>
        ) : (
          <div>
            <p>{`Contenuto salvato su object storage (${data.content_size} byte).`}</p>
            {data.content_url && (
              <button disabled={busyAction !== null} onClick={() => void downloadContent()}>
                {busyAction === "download" ? "Download…" : "Scarica contenuto completo"}
              </button>
            )}
          </div>
        )}
      </div>

      <div className="toolbar">
        <button
          disabled={busyAction !== null}
          onClick={() => void setStatus(data.status === "unread" ? "read" : "unread")}
        >
          {data.status === "unread" ? "Segna come letta" : "Segna come non letta"}
        </button>
        <button disabled={busyAction !== null} onClick={() => void setVerified(!data.verified)}>
          {data.verified ? "Segna come non verificata" : "Segna come verificata"}
        </button>
        {role !== null && DELETE_ALLOWED_ROLES.includes(role) && (
          <button disabled={busyAction !== null} onClick={() => void remove()}>
            {busyAction === "delete" ? "Eliminazione…" : "Elimina"}
          </button>
        )}
      </div>
    </div>
  );
}
