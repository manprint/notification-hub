import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type { ApiError, DeleteImpactOut, GroupOut } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import { useSession } from "../hooks/useSession";
import { ADMIN_ROLES, hasRole } from "../lib/roles";

function EditGroupForm({ group, onDone }: { group: GroupOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description ?? "");
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPatch(`/api/v1/groups/${group.id}`, { name, description: description || null });
      await queryClient.invalidateQueries({ queryKey: ["groups"] });
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <div className="form-row">
        <label htmlFor={`group-edit-name-${group.id}`}>Nome</label>
        <input
          id={`group-edit-name-${group.id}`}
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`group-edit-description-${group.id}`}>Descrizione</label>
        <input
          id={`group-edit-description-${group.id}`}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </div>
      <div className="toolbar">
        <button type="submit" className="primary">
          Salva
        </button>
        <button type="button" onClick={onDone}>
          Annulla
        </button>
      </div>
    </form>
  );
}

function DeleteGroupButton({ group }: { group: GroupOut }) {
  const [open, setOpen] = useState(false);
  const [impact, setImpact] = useState<DeleteImpactOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const queryClient = useQueryClient();

  async function openDialog() {
    setError(null);
    try {
      const data = await apiGet<DeleteImpactOut>(`/api/v1/groups/${group.id}/delete-impact`);
      setImpact(data);
      setOpen(true);
    } catch (err) {
      setError(err as ApiError);
    }
  }

  async function confirmDelete() {
    try {
      await apiDelete(`/api/v1/groups/${group.id}?confirm=${encodeURIComponent(group.name)}`);
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["groups"] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <div>
      {error && <ErrorBanner error={error} />}
      {open && impact ? (
        <ConfirmDialog
          title={`Elimina gruppo "${group.name}"`}
          expectedText={group.name}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setOpen(false)}
        >
          <p>Verranno eliminati in cascata:</p>
          <ul>
            <li>{impact.receivers} receiver</li>
            <li>{impact.notifications} notifiche</li>
            <li>{impact.deliveries} consegne</li>
          </ul>
        </ConfirmDialog>
      ) : (
        <button onClick={() => void openDialog()}>Elimina gruppo</button>
      )}
    </div>
  );
}

export default function GroupsPage() {
  const { role } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: groups, isLoading, error } = useQuery<GroupOut[], ApiError>({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });

  const [query, setQuery] = useState("");
  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState<ApiError | null>(null);
  const [editingGroup, setEditingGroup] = useState<GroupOut | null>(null);

  async function createGroup(event: React.FormEvent) {
    event.preventDefault();
    setCreateError(null);
    try {
      await apiPost("/api/v1/groups", { name: newName });
      setNewName("");
      await queryClient.invalidateQueries({ queryKey: ["groups"] });
    } catch (err) {
      setCreateError(err as ApiError);
    }
  }

  const q = query.trim().toLowerCase();
  const filtered = q
    ? (groups ?? []).filter(
        (g) =>
          g.name.toLowerCase().includes(q) ||
          (g.description ?? "").toLowerCase().includes(q),
      )
    : (groups ?? []);

  const columns: DataTableColumn<GroupOut>[] = [
    {
      key: "name",
      header: "Nome",
      render: (g) => (
        <>
          <span>{g.name}</span>
          {g.description && <span className="card-hint"> — {g.description}</span>}
        </>
      ),
    },
    {
      key: "receiver_count",
      header: "Receiver configurati",
      render: (g) => <span>{g.receiver_count}</span>,
    },
    {
      key: "actions",
      header: "Azioni",
      render: (g) => (
        <div className="row-actions">
          <button onClick={() => navigate(`/groups/${g.id}`)}>Apri</button>
          {hasRole(role, ADMIN_ROLES) && (
            <>
              <button onClick={() => setEditingGroup(g)}>Modifica gruppo</button>
              <DeleteGroupButton group={g} />
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <h1>Gruppi</h1>
      {error && <ErrorBanner error={error} />}

      {hasRole(role, ADMIN_ROLES) && (
        <div className="card">
          <h3>Nuovo gruppo</h3>
          {createError && <ErrorBanner error={createError} />}
          <form onSubmit={(event) => void createGroup(event)}>
            <div className="form-row">
              <label htmlFor="group-name">Nome</label>
              <input
                id="group-name"
                required
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
            </div>
            <button type="submit" className="primary">
              Crea gruppo
            </button>
          </form>
        </div>
      )}

      <div className="group-search">
        <input
          type="search"
          aria-label="Cerca gruppi"
          placeholder="Cerca gruppi…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <DataTable
        columns={columns}
        rows={filtered}
        rowKey={(g) => g.id}
        loading={isLoading}
        emptyMessage={q ? "Nessun gruppo corrisponde alla ricerca." : "Nessun gruppo configurato."}
      />

      {editingGroup && (
        <div className="card">
          <EditGroupForm group={editingGroup} onDone={() => setEditingGroup(null)} />
        </div>
      )}
    </div>
  );
}
