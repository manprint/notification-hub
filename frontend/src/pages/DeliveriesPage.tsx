import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import type { ApiError, DeliveryOut, DeliveryStatus } from "../api/types";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import StatusPill from "../components/StatusPill";
import { useSession } from "../hooks/useSession";

const STATUSES: DeliveryStatus[] = ["pending", "sending", "sent", "failed", "dead"];
const RETRY_ALLOWED_ROLES = ["owner", "admin", "member"];

export default function DeliveriesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = (searchParams.get("status") as DeliveryStatus | null) ?? undefined;
  const queryClient = useQueryClient();
  const { role } = useSession();

  const { data, isLoading, error } = useQuery<DeliveryOut[], ApiError>({
    queryKey: ["deliveries", status],
    queryFn: () => apiGet<DeliveryOut[]>("/api/v1/deliveries", { status }),
  });

  async function retry(id: string) {
    await apiPost(`/api/v1/deliveries/${id}/retry`);
    await queryClient.invalidateQueries({ queryKey: ["deliveries"] });
  }

  const canRetry = role !== null && RETRY_ALLOWED_ROLES.includes(role);

  const columns: DataTableColumn<DeliveryOut>[] = [
    { key: "status", header: "Stato", render: (d) => <StatusPill status={d.status} /> },
    { key: "attempts", header: "Tentativi", render: (d) => d.attempts },
    { key: "response_code", header: "Codice", render: (d) => d.response_code ?? "—" },
    { key: "last_error", header: "Errore", render: (d) => d.last_error ?? "—" },
    {
      key: "next_attempt_at",
      header: "Prossimo tentativo",
      render: (d) => new Date(d.next_attempt_at).toLocaleString("it-IT"),
    },
    {
      key: "actions",
      header: "",
      render: (d) =>
        d.status === "dead" && canRetry ? (
          <button onClick={() => void retry(d.id)}>Ri-accoda</button>
        ) : null,
    },
  ];

  return (
    <div>
      <h1>Consegne</h1>
      {error && <ErrorBanner error={error} />}

      <div className="toolbar">
        <select
          value={status ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              if (value) next.set("status", value);
              else next.delete("status");
              return next;
            });
          }}
        >
          <option value="">Tutti gli stati</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(d) => d.id}
        loading={isLoading}
        emptyMessage="Nessuna consegna trovata."
      />
    </div>
  );
}
