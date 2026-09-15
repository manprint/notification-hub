import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPatch } from "../api/client";
import type { ApiError, NotificationDetailOut, NotificationStatus } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import Detail from "../components/Detail";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";
import StatusPill from "../components/StatusPill";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { formatBytes, formatDateTime } from "../lib/format";
import { formatDurationMs } from "../lib/duration";
import { isSurveillanceSource, phaseLabel, severitySourceLabel } from "../lib/severitySource";

const DELETE_ALLOWED_ROLES = ["owner", "admin", "member"];
// L'audit e' di owner e admin (backend: require_admin): agli altri il
// collegamento non si mostra, prenderebbero 403.
const AUDIT_ROLES = ["owner", "admin"];

export default function NotificationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { role } = useSession();
  const { busy: busyAction, error: actionError, run } = useAction();
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const { data, isLoading, error } = useQuery<NotificationDetailOut, ApiError>({
    queryKey: ["notification", id],
    queryFn: () => apiGet<NotificationDetailOut>(`/api/v1/notifications/${id}`),
    enabled: Boolean(id),
  });

  if (isLoading) return <EmptyState message="Caricamento…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return null;

  async function setStatus(status: NotificationStatus) {
    await run(
      async () => {
        await apiPatch(`/api/v1/notifications/${id}`, { status });
        await queryClient.invalidateQueries({ queryKey: ["notification", id] });
      },
      {
        name: "status",
        success:
          status === "read" ? "Notifica segnata come letta." : "Notifica riportata a non letta.",
      },
    );
  }

  async function setVerified(verified: boolean) {
    await run(
      async () => {
        await apiPatch(`/api/v1/notifications/${id}`, { verified });
        await queryClient.invalidateQueries({ queryKey: ["notification", id] });
      },
      {
        name: "verified",
        success: verified
          ? "Notifica segnata come verificata."
          : "Verifica rimossa dalla notifica.",
      },
    );
  }

  async function remove() {
    setConfirmingDelete(false);
    const ok = await run(async () => apiDelete(`/api/v1/notifications/${id}`), {
      name: "delete",
      success: "Notifica eliminata.",
    });
    if (ok) navigate("/notifications", { replace: true });
  }

  // L'endpoint del contenuto richiede il Bearer token: un <a href download>
  // partiva senza header Authorization e riceveva 401. Va scaricato dal client
  // API e consegnato al browser come blob.
  async function downloadContent() {
    await run(
      async () => {
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
      },
      { name: "download" },
    );
  }

  const canDelete = role !== null && DELETE_ALLOWED_ROLES.includes(role);
  const canSeeAudit = role !== null && AUDIT_ROLES.includes(role);

  return (
    <div>
      <Link className="back-link" to="/notifications">
        ← Torna alle notifiche
      </Link>
      <div className="page-header">
        <h1>Dettaglio notifica</h1>
        <div className="page-header-actions">
          <button
            disabled={busyAction !== null}
            onClick={() => void setStatus(data.status === "unread" ? "read" : "unread")}
          >
            {data.status === "unread" ? "Segna come letta" : "Segna come non letta"}
          </button>
          <button disabled={busyAction !== null} onClick={() => void setVerified(!data.verified)}>
            {data.verified ? "Segna come non verificata" : "Segna come verificata"}
          </button>
          {/* L'id della notifica non e' esposto da nessuna parte, e non deve
              esserlo: il filtro dell'audit si riempie da qui. */}
          {canSeeAudit && (
            <Link className="button-link" to={`/settings/letture-e-verifiche?notification_id=${id}`}>
              Chi l'ha letta o verificata
            </Link>
          )}
          {canDelete && (
            <button
              className="danger"
              disabled={busyAction !== null}
              onClick={() => setConfirmingDelete(true)}
            >
              {busyAction === "delete" ? "Eliminazione…" : "Elimina"}
            </button>
          )}
        </div>
      </div>
      {actionError && <ErrorBanner error={actionError} />}

      <div className="card">
        <div className="status-cell detail-status">
          <SeverityBadge severity={data.severity} />
          <StatusPill status={data.status} />
          <span className={`status-pill${data.verified ? " verified" : ""}`}>
            {data.verified ? "Verificata" : "Non verificata"}
          </span>
        </div>

        <div className="detail-grid">
          <Detail label="Ricevuta">{formatDateTime(data.received_at)}</Detail>
          <Detail label="Origine della severity">
            <strong>{severitySourceLabel(data.severity_source)}</strong>
            {data.severity_source === "rule" && data.matched_pattern && (
              <div className="cell-diagnostics">
                pattern vincente: <code>{data.matched_pattern}</code>
              </div>
            )}
          </Detail>
          {data.duration_ms !== null && (
            <Detail label="Durata esecuzione">{formatDurationMs(data.duration_ms)}</Detail>
          )}
          {data.exit_code !== null && <Detail label="Exit code">{data.exit_code}</Detail>}
          {data.phase !== null && (
            <Detail label="Fase dell'esecuzione">
              {phaseLabel(data.phase)}
              {data.phase === "start" && (
                <div className="cell-diagnostics">
                  ping di avvio: dice che il job è partito, non com'è andato
                </div>
              )}
            </Detail>
          )}
          {data.source_ip && <Detail label="Sorgente">{data.source_ip}</Detail>}
          {/* Chi ha gestito la notifica: la domanda ricorrente, a cui qui
              risponde il solo stato corrente. Lo storico dei passaggi (e dei
              ripristini) vive nell'audit, riservato a owner e admin. */}
          {data.read_by_email && (
            <Detail label="Letta da">
              <strong>{data.read_by_email}</strong>
              {data.read_at && (
                <div className="cell-diagnostics">il {formatDateTime(data.read_at)}</div>
              )}
            </Detail>
          )}
          {data.verified_by_email && (
            <Detail label="Verificata da">
              <strong>{data.verified_by_email}</strong>
              {data.verified_at && (
                <div className="cell-diagnostics">il {formatDateTime(data.verified_at)}</div>
              )}
            </Detail>
          )}
        </div>

        {isSurveillanceSource(data.severity_source) && (
          <p className="card-hint spaced-top">
            Notifica generata da NotifyHub, non inviata da nessuno: la sorveglianza dell'attesa del
            receiver si è accorta che{" "}
            {data.severity_source === "missing"
              ? "un invio previsto non è arrivato"
              : "gli invii sono ripresi dopo un'assenza"}
            .
          </p>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Contenuto</h3>
          {data.content === null && data.content_url && (
            <div className="card-header-actions">
              <button disabled={busyAction !== null} onClick={() => void downloadContent()}>
                {busyAction === "download" ? "Download…" : "Scarica contenuto completo"}
              </button>
            </div>
          )}
        </div>
        {data.content !== null ? (
          <pre>{data.content}</pre>
        ) : (
          <p className="card-hint">
            {`Contenuto salvato su object storage (${formatBytes(data.content_size)}).`}
          </p>
        )}
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title="Elimina questa notifica"
          confirmLabel="Elimina"
          onConfirm={() => void remove()}
          onCancel={() => setConfirmingDelete(false)}
        >
          <p>
            L'eliminazione è definitiva e toglie anche le consegne collegate. L'audit conserva
            traccia di chi l'ha gestita.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
