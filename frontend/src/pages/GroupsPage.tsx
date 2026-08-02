import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiDelete, apiGet, apiPost } from "../api/client";
import type { ApiError, DeleteImpactOut, GroupOut, ReceiverOut } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorBanner from "../components/ErrorBanner";

function GroupReceivers({ groupId }: { groupId: string }) {
  const { data: receivers } = useQuery({
    queryKey: ["receivers", groupId],
    queryFn: () => apiGet<ReceiverOut[]>(`/api/v1/groups/${groupId}/receivers`),
  });

  if (!receivers || receivers.length === 0) {
    return <p style={{ color: "var(--color-text-muted)" }}>Nessun receiver in questo gruppo.</p>;
  }

  return (
    <ul>
      {receivers.map((r) => (
        <li key={r.id}>
          <Link to={`/receivers/${r.id}`}>{r.name}</Link> — <code>{r.slug}</code>
        </li>
      ))}
    </ul>
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

      {isLoading && <p>Caricamento…</p>}

      {groups?.map((group) => (
        <div className="card" key={group.id}>
          <h3>{group.name}</h3>
          {group.description && <p>{group.description}</p>}
          <GroupReceivers groupId={group.id} />
          <DeleteGroupButton group={group} />
        </div>
      ))}
    </div>
  );
}
