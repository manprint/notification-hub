import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
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

/** Limiti del backend (schemas/group.py): il modulo non blocca valori che l'API accetta. */
const NAME_MAX = 255;
const DESCRIPTION_MAX = 1024;

function EditGroupForm({ group, onDone }: { group: GroupOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
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
          // Sempre presente, anche vuota: "" esplicito svuota la descrizione.
          // Il campo omesso (o null, per il backend di prima) la lasciava com'era,
          // e il modulo si chiudeva con "Gruppo aggiornato" senza averla tolta.
          description: description.trim(),
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
    <Modal title={`Modifica "${group.name}"`} onClose={onDone} busy={busy !== null}>
      <form onSubmit={(event) => void handleSubmit(event)}>
        {error && <ErrorBanner error={error} />}
        <RequiredLegend />
        <Field id={nameId} label="Nome" required error={nameError}>
          <input
            {...fieldAria(nameId, { error: nameError })}
            required
            maxLength={NAME_MAX}
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
            maxLength={DESCRIPTION_MAX}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Salvataggio…" : "Salva"}
          </button>
          <button type="button" disabled={busy !== null} onClick={onDone}>
            Annulla
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Azioni di una riga del gruppo. Il banner dell'errore e la finestra di conferma
 *  stanno fuori da `.row-actions`: lì il testo non va a capo e allargherebbe la
 *  colonna (e la tabella) con un messaggio lungo. */
function GroupRowActions({
  group,
  canAdmin,
  onEdit,
}: {
  group: GroupOut;
  canAdmin: boolean;
  onEdit: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [impact, setImpact] = useState<DeleteImpactOut | null>(null);
  const [impactError, setImpactError] = useState<ApiError | null>(null);
  const queryClient = useQueryClient();
  const { error: deleteError, run } = useAction();

  async function openDialog() {
    setImpactError(null);
    try {
      const data = await apiGet<DeleteImpactOut>(`/api/v1/groups/${group.id}/delete-impact`);
      setImpact(data);
      setOpen(true);
    } catch (err) {
      setImpactError(err as ApiError);
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
      <div className="row-actions">
        <Link className="button-link" to={`/groups/${group.id}`}>
          Apri
        </Link>
        {canAdmin && (
          <>
            <button onClick={onEdit}>Modifica gruppo</button>
            <button className="danger" onClick={() => void openDialog()}>
              Elimina gruppo
            </button>
          </>
        )}
      </div>
      {impactError && <ErrorBanner error={impactError} />}
      {open && impact && (
        <ConfirmDialog
          title={`Elimina gruppo "${group.name}"`}
          expectedText={group.name}
          confirmLabel="Elimina gruppo"
          // La promessa, non `void`: il dialogo resta occupato fino alla risposta,
          // e un doppio click non manda una seconda DELETE.
          onConfirm={confirmDelete}
          onCancel={() => setOpen(false)}
        >
          {/* Il motivo del rifiuto resta nel dialogo: il toast scompare dopo pochi secondi. */}
          {deleteError && <ErrorBanner error={deleteError} />}
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
  const [newDescription, setNewDescription] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function createGroup(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newName.trim() === "") {
      setNameError("Il nome del gruppo è obbligatorio.");
      return;
    }
    setNameError(null);
    const ok = await run(
      async () => {
        await apiPost("/api/v1/groups", {
          name: newName.trim(),
          ...(newDescription.trim() !== "" ? { description: newDescription.trim() } : {}),
        });
        await queryClient.invalidateQueries({ queryKey: ["groups"] });
      },
      { success: `Gruppo "${newName.trim()}" creato.` },
    );
    if (ok) {
      setNewName("");
      setNewDescription("");
    }
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
            maxLength={NAME_MAX}
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
        </Field>
        <Field
          id="group-new-description"
          label="Descrizione"
          optional
          hint="Compare nell'elenco dei gruppi e aiuta chi non li ha creati."
        >
          <input
            {...fieldAria("group-new-description", { hint: true })}
            maxLength={DESCRIPTION_MAX}
            value={newDescription}
            onChange={(event) => setNewDescription(event.target.value)}
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
  const canAdmin = hasRole(role, ADMIN_ROLES);
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
        <GroupRowActions group={g} canAdmin={canAdmin} onEdit={() => setEditingGroup(g)} />
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

      {canAdmin && <NewGroupForm />}

      <div className="group-search">
        <input
          type="search"
          aria-label="Cerca gruppi"
          placeholder="Cerca gruppi…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <div className="card">
        <DataTable
          columns={columns}
          rows={filtered}
          rowKey={(g) => g.id}
          loading={isLoading}
          error={error}
          emptyMessage={q ? "Nessun gruppo corrisponde alla ricerca." : "Nessun gruppo configurato."}
        />
      </div>

      {editingGroup && (
        <EditGroupForm group={editingGroup} onDone={() => setEditingGroup(null)} />
      )}
    </div>
  );
}
