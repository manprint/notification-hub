import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type { ApiError, DeleteImpactOut, GroupOut, ReceiverOut, Severity } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorBanner from "../components/ErrorBanner";
import { useSession } from "../hooks/useSession";
import { ADMIN_ROLES, hasRole } from "../lib/roles";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

function NewReceiverForm({ groupId }: { groupId: string }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>("info");
  const [error, setError] = useState<ApiError | null>(null);

  async function createReceiver(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPost(`/api/v1/groups/${groupId}/receivers`, {
        name,
        default_severity: defaultSeverity,
      });
      setName("");
      setDefaultSeverity("info");
      await queryClient.invalidateQueries({ queryKey: ["receivers", groupId] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <form onSubmit={(event) => void createReceiver(event)} className="toolbar">
      {error && <ErrorBanner error={error} />}
      <input
        placeholder="Nome receiver"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <select
        value={defaultSeverity}
        onChange={(event) => setDefaultSeverity(event.target.value as Severity)}
      >
        {SEVERITIES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <button type="submit" className="primary">
        Aggiungi receiver
      </button>
    </form>
  );
}

function GroupReceivers({ groupId }: { groupId: string }) {
  const { data: receivers } = useQuery({
    queryKey: ["receivers", groupId],
    queryFn: () => apiGet<ReceiverOut[]>(`/api/v1/groups/${groupId}/receivers`),
  });

  return (
    <div>
      {!receivers || receivers.length === 0 ? (
        <p style={{ color: "var(--color-text-muted)" }}>Nessun receiver in questo gruppo.</p>
      ) : (
        <ul>
          {receivers.map((r) => (
            <li key={r.id}>
              <Link to={`/receivers/${r.id}`}>{r.name}</Link> — <code>{r.slug}</code>
            </li>
          ))}
        </ul>
      )}
      <NewReceiverForm groupId={groupId} />
    </div>
  );
}

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

function GroupCard({ group }: { group: GroupOut }) {
  const { role } = useSession();
  const [editing, setEditing] = useState(false);
  const canManage = hasRole(role, ADMIN_ROLES);

  return (
    <div className="card">
      {editing ? (
        <EditGroupForm group={group} onDone={() => setEditing(false)} />
      ) : (
        <>
          <h3>{group.name}</h3>
          {group.description && <p>{group.description}</p>}
        </>
      )}
      <GroupReceivers groupId={group.id} />
      {canManage && !editing && (
        <div className="toolbar">
          <button onClick={() => setEditing(true)}>Modifica gruppo</button>
          <DeleteGroupButton group={group} />
        </div>
      )}
    </div>
  );
}

export default function GroupsPage() {
  const { role } = useSession();
  const queryClient = useQueryClient();
  const { data: groups, isLoading, error } = useQuery<GroupOut[], ApiError>({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });

  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState<ApiError | null>(null);

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

      {isLoading && <p>Caricamento…</p>}

      {groups?.map((group) => (
        <GroupCard key={group.id} group={group} />
      ))}
    </div>
  );
}
