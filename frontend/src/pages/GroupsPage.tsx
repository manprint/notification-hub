import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type { ApiError, DeleteImpactOut, GroupOut } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import Modal from "../components/Modal";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { ADMIN_ROLES, hasRole } from "../lib/roles";

function EditGroupForm({ group, onDone }: { group: GroupOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (name.trim() === "") {
      setNameError("Il nome del gruppo è obbligatorio.");
      return;
    }
    setNameError(null);
    const ok = await run(
      async () => {
        await apiPatch(`/api/v1/groups/${group.id}`, {
          name: name.trim(),
          description: description.trim() || null,
        });
        await queryClient.invalidateQueries({ queryKey: ["groups"] });
      },
      { success: "Gruppo aggiornato." },
    );
    // Il modulo resta aperto se il salvataggio fallisce (nome duplicato → 409):
    // chiuderlo comunque farebbe sparire il testo insieme all'errore.
    if (ok) onDone();
  }

  const nameId = `group-edit-name-${group.id}`;
  const descriptionId = `group-edit-description-${group.id}`;

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <RequiredLegend />
      <Field id={nameId} label="Nome" required error={nameError}>
        <input
          {...fieldAria(nameId, { error: nameError })}
          required
          maxLength={120}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </Field>
      <Field
        id={descriptionId}
        label="Descrizione"
        optional
        hint="Compare nell'elenco dei gruppi e aiuta chi non li ha creati."
      >
        <input
          {...fieldAria(descriptionId, { hint: true })}
          maxLength={500}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>
      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy !== null}>
          {busy !== null ? "Salvataggio…" : "Salva"}
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
  const { run } = useAction();

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
    const ok = await run(
      async () => {
        await apiDelete(`/api/v1/groups/${group.id}?confirm=${encodeURIComponent(group.name)}`);
        await queryClient.invalidateQueries({ queryKey: ["groups"] });
      },
      { success: `Gruppo "${group.name}" eliminato.` },
    );
    if (ok) setOpen(false);
  }

  return (
    <>
      {error && <ErrorBanner error={error} />}
      <button className="danger" onClick={() => void openDialog()}>
        Elimina gruppo
      </button>
      {open && impact && (
        <ConfirmDialog
          title={`Elimina gruppo "${group.name}"`}
          expectedText={group.name}
          confirmLabel="Elimina gruppo"
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
      )}
    </>
  );
}

function NewGroupForm() {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function createGroup(event: React.FormEvent) {
    event.preventDefault();
    if (newName.trim() === "") {
      setNameError("Il nome del gruppo è obbligatorio.");
      return;
    }
    setNameError(null);
    const ok = await run(
      async () => {
        await apiPost("/api/v1/groups", { name: newName.trim() });
        await queryClient.invalidateQueries({ queryKey: ["groups"] });
      },
      { success: `Gruppo "${newName.trim()}" creato.` },
    );
    if (ok) setNewName("");
  }

  return (
    // Chiuso di default: la pagina serve a leggere l'elenco, non a creare un
    // gruppo ogni volta che la si apre.
    <details className="card collapsible">
      <summary>Nuovo gruppo</summary>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void createGroup(event)}>
        <RequiredLegend />
        <Field
          id="group-name"
          label="Nome"
          required
          error={nameError}
          hint="Un gruppo raccoglie i receiver di uno stesso ambito (una macchina, un cliente, un servizio)."
        >
          <input
            {...fieldAria("group-name", { hint: true, error: nameError })}
            required
            maxLength={120}
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Creazione…" : "Crea gruppo"}
          </button>
        </div>
      </form>
    </details>
  );
}

export default function GroupsPage() {
  const { role } = useSession();
  const navigate = useNavigate();
  const {
    data: groups,
    isLoading,
    error,
  } = useQuery<GroupOut[], ApiError>({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });

  const [query, setQuery] = useState("");
  const [editingGroup, setEditingGroup] = useState<GroupOut | null>(null);

  const q = query.trim().toLowerCase();
  const filtered = q
    ? (groups ?? []).filter(
        (g) =>
          g.name.toLowerCase().includes(q) || (g.description ?? "").toLowerCase().includes(q),
      )
    : (groups ?? []);

  const columns: DataTableColumn<GroupOut>[] = [
    {
      key: "name",
      header: "Nome",
      render: (g) => (
        <div className="cell-preview">
          <span>{g.name}</span>
          {g.description && <div className="cell-diagnostics">{g.description}</div>}
        </div>
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
      <div className="page-header">
        <h1>Gruppi</h1>
      </div>
      <p className="page-subtitle">
        Ogni gruppo raccoglie i receiver che condividono destinatari e soglie: è l'unità con cui si
        danno i permessi e si collegano i canali.
      </p>
      {error && <ErrorBanner error={error} />}

      {hasRole(role, ADMIN_ROLES) && <NewGroupForm />}

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
        <Modal title={`Modifica "${editingGroup.name}"`} onClose={() => setEditingGroup(null)}>
          <EditGroupForm group={editingGroup} onDone={() => setEditingGroup(null)} />
        </Modal>
      )}
    </div>
  );
}
