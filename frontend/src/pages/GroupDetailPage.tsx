import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../api/client";
import type { ApiError, GroupOut, ReceiverOut } from "../api/types";
import CopyButton from "../components/CopyButton";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import NewReceiverForm from "../components/NewReceiverForm";
import SeverityBadge from "../components/SeverityBadge";
import { useSession } from "../hooks/useSession";
import { MEMBER_ROLES, hasRole } from "../lib/roles";

export default function GroupDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { role } = useSession();

  const {
    data: group,
    isLoading: groupLoading,
    error: groupError,
  } = useQuery<GroupOut, ApiError>({
    queryKey: ["group", id],
    queryFn: () => apiGet<GroupOut>(`/api/v1/groups/${id}`),
    enabled: Boolean(id),
  });

  const {
    data: receivers,
    isLoading: receiversLoading,
    error: receiversError,
  } = useQuery<ReceiverOut[], ApiError>({
    queryKey: ["receivers", id],
    queryFn: () => apiGet<ReceiverOut[]>(`/api/v1/groups/${id}/receivers`),
    enabled: Boolean(id),
  });

  if (groupLoading) return <EmptyState message="Caricamento…" />;
  if (groupError) return <ErrorBanner error={groupError} />;

  const columns: DataTableColumn<ReceiverOut>[] = [
    {
      key: "name",
      header: "Nome receiver",
      render: (r) => <Link to={`/receivers/${r.id}`}>{r.name}</Link>,
    },
    {
      key: "status",
      header: "Stato",
      render: (r) => (
        <div className="status-cell">
          <span className={r.status === "active" ? "status-pill ok" : "status-pill warn"}>
            {r.status === "active" ? "Attivo" : "Disabilitato"}
          </span>
          {/* Il ritardo della sorveglianza si vede qui e non solo aprendo il
              receiver: è il motivo per cui si apre questa pagina. */}
          {r.expected_late && <span className="status-pill danger">in ritardo</span>}
        </div>
      ),
    },
    {
      key: "slug",
      header: "Slug",
      render: (r) => (
        <div className="slug-cell">
          <code title={r.slug}>{r.slug}</code>
          <CopyButton value={r.ingest_url} />
        </div>
      ),
    },
    {
      key: "default_severity",
      header: "Severity",
      render: (r) => <SeverityBadge severity={r.default_severity} />,
    },
  ];

  return (
    <div>
      <Link className="back-link" to="/groups">
        ← Torna ai gruppi
      </Link>
      <div className="page-header">
        <h1>
          Gruppo <span className="title-separator">/</span>{" "}
          <span className="title-context">{group?.name ?? "Gruppo"}</span>
        </h1>
      </div>
      {group?.description && <p className="page-subtitle">{group.description}</p>}
      {receiversError && <ErrorBanner error={receiversError} />}

      <div className="card group-receivers-table">
        <div className="card-header">
          <h3>Receiver del gruppo</h3>
          <span className="card-header-actions text-muted text-sm">
            {(receivers ?? []).length} configurati
          </span>
        </div>
        <DataTable
          columns={columns}
          rows={receivers ?? []}
          rowKey={(r) => r.id}
          loading={receiversLoading}
          emptyMessage="Nessun receiver in questo gruppo."
        />
      </div>

      {hasRole(role, MEMBER_ROLES) && <NewReceiverForm groupId={id ?? ""} />}
    </div>
  );
}
