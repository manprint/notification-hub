import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../api/client";
import type { ApiError, GroupOut, ReceiverOut } from "../api/types";
import CopyButton from "../components/CopyButton";
import DataTable, { type DataTableColumn } from "../components/DataTable";
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

  if (groupLoading) return <p>Caricamento…</p>;
  if (groupError) return <ErrorBanner error={groupError} />;

  const columns: DataTableColumn<ReceiverOut>[] = [
    {
      key: "name",
      header: "Nome receiver",
      render: (r) => <Link to={`/receivers/${r.id}`}>{r.name}</Link>,
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
      <h1>{group?.name ?? "Gruppo"}</h1>
      {receiversError && <ErrorBanner error={receiversError} />}
      <div className="group-receivers-table">
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
