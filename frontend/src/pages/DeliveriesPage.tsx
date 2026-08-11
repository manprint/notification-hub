import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import type { ApiError, DeliveryChannelOut, DeliveryOut, DeliveryStatus } from "../api/types";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";
import StatusPill from "../components/StatusPill";
import { useSession } from "../hooks/useSession";
import { MEMBER_ROLES, hasRole } from "../lib/roles";

const STATUSES: DeliveryStatus[] = ["pending", "sending", "sent", "failed", "dead"];

const STATUS_HELP: Record<DeliveryStatus, string> = {
  pending: "in coda, non ancora inviata",
  sending: "invio in corso",
  sent: "consegnata al webhook",
  failed: "tentativo fallito, ritenta in automatico",
  dead: "esauriti i tentativi, serve un ri-accodamento manuale",
};

export default function DeliveriesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = (searchParams.get("status") as DeliveryStatus | null) ?? undefined;
  const channelId = searchParams.get("channel_id") ?? undefined;
  const queryClient = useQueryClient();
  const { role } = useSession();
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery<DeliveryOut[], ApiError>({
    queryKey: ["deliveries", status, channelId],
    queryFn: () => apiGet<DeliveryOut[]>("/api/v1/deliveries", { status, channel_id: channelId }),
  });

  const { data: channels } = useQuery<DeliveryChannelOut[], ApiError>({
    queryKey: ["channels"],
    queryFn: () => apiGet<DeliveryChannelOut[]>("/api/v1/channels"),
  });

  function setParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  }

  async function retry(id: string) {
    setActionError(null);
    setRetryingId(id);
    try {
      await apiPost(`/api/v1/deliveries/${id}/retry`);
      await queryClient.invalidateQueries({ queryKey: ["deliveries"] });
    } catch (err) {
      setActionError(err as ApiError);
    } finally {
      setRetryingId(null);
    }
  }

  const canRetry = hasRole(role, MEMBER_ROLES);

  const columns: DataTableColumn<DeliveryOut>[] = [
    {
      key: "notification",
      header: "Notifica inoltrata",
      render: (d) => (
        <div className="cell-preview">
          <Link to={`/notifications/${d.notification_id}`}>{d.content_preview || "(vuota)"}</Link>
          <div className="cell-diagnostics">
            <SeverityBadge severity={d.severity} /> da {d.receiver_name} ·{" "}
            {new Date(d.received_at).toLocaleString("it-IT")}
          </div>
        </div>
      ),
    },
    { key: "channel_name", header: "Canale", render: (d) => d.channel_name },
    {
      key: "status",
      header: "Stato",
      render: (d) => (
        <div>
          <StatusPill status={d.status} />
          <div className="cell-diagnostics">{STATUS_HELP[d.status]}</div>
        </div>
      ),
    },
    {
      key: "attempts",
      header: "Tentativi",
      render: (d) => (
        <div>
          {d.attempts}
          {d.sent_at && (
            <div className="cell-diagnostics">
              inviata: {new Date(d.sent_at).toLocaleString("it-IT")}
            </div>
          )}
          {!d.sent_at && d.status !== "sent" && (
            <div className="cell-diagnostics">
              prossimo tentativo: {new Date(d.next_attempt_at).toLocaleString("it-IT")}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "last_error",
      header: "Esito",
      render: (d) => (
        <div className="cell-diagnostics">
          {d.response_code ? `HTTP ${d.response_code}` : "—"}
          {d.last_error && <div>{d.last_error}</div>}
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (d) =>
        d.status === "dead" && canRetry ? (
          <button disabled={retryingId !== null} onClick={() => void retry(d.id)}>
            {retryingId === d.id ? "Ri-accodamento…" : "Ri-accoda"}
          </button>
        ) : null,
    },
  ];

  return (
    <div>
      <h1>Consegne</h1>
      <p className="card-hint">
        Storico degli inoltri verso Slack e Google Chat: una riga per ogni notifica spedita a un canale.
        Serve a capire perché un messaggio non è arrivato — codice HTTP, errore e tentativi. Le consegne
        in stato «morta» hanno esaurito i 5 tentativi e si ri-accodano a mano.
      </p>
      {error && <ErrorBanner error={error} />}
      {actionError && <ErrorBanner error={actionError} />}

      <div className="toolbar">
        <select value={status ?? ""} onChange={(event) => setParam("status", event.target.value)}>
          <option value="">Tutti gli stati</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          value={channelId ?? ""}
          onChange={(event) => setParam("channel_id", event.target.value)}
        >
          <option value="">Tutti i canali</option>
          {channels?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(d) => d.id}
        loading={isLoading}
        emptyMessage="Nessuna consegna trovata: nessuna notifica ha ancora superato la soglia di un canale."
      />
    </div>
  );
}
