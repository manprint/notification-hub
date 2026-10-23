import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type {
  ApiError,
  GroupOut,
  InvitationOut,
  InvitationSummaryOut,
  UserOut,
  UserRole,
} from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import CopyButton from "../components/CopyButton";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import SaveIndicator from "../components/SaveIndicator";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { formatDateTime, roleLabel, userStatusLabel } from "../lib/format";
import { ADMIN_ROLES, hasRole } from "../lib/roles";

const ROLES: UserRole[] = ["owner", "admin", "member", "viewer"];
const MIN_PASSWORD_LENGTH = 12;

/** Ruoli che la sessione può assegnare. Il ruolo owner lo concede solo un
 *  owner (il backend rifiuta con 403): offrirlo a un admin voleva dire un
 *  modulo che fallisce sempre. */
function assignableRoles(sessionRole: UserRole | null): UserRole[] {
  return sessionRole === "owner" ? ROLES : ROLES.filter((r) => r !== "owner");
}

const ROLE_HINTS: Record<UserRole, string> = {
  owner: "tutto, comprese le quote del tenant",
  admin: "utenti, canali, gruppi e audit",
  member: "gruppi assegnati: receiver, regole, notifiche",
  viewer: "sola lettura sulle notifiche",
};

function GroupPicker({
  groups,
  value,
  onChange,
  disabled = false,
}: {
  groups: GroupOut[];
  value: string[];
  onChange: (groupIds: string[]) => void;
  /** Durante il salvataggio: la lista nuova si calcola da `value`, che si
   *  aggiorna solo a salvataggio finito. Un secondo click nel frattempo
   *  partirebbe dalla lista vecchia e cancellerebbe il primo. */
  disabled?: boolean;
}) {
  function toggle(groupId: string, checked: boolean) {
    // Un controllo disabilitato non salva, neanche se un click sintetico arriva
    // comunque al gestore: nel test il secondo click finiva per salvare due volte.
    if (disabled) return;
    onChange(checked ? [...value, groupId] : value.filter((id) => id !== groupId));
  }

  if (groups.length === 0) {
    return <p className="group-picker-empty">Nessun gruppo di receiver disponibile.</p>;
  }

  return (
    <div className="group-picker">
      {groups.map((g) => (
        <label key={g.id}>
          <input
            type="checkbox"
            checked={value.includes(g.id)}
            disabled={disabled}
            onChange={(event) => toggle(g.id, event.target.checked)}
          />
          {g.name}
        </label>
      ))}
    </div>
  );
}

/** I gruppi assegnati a un'utenza, modificabili dalla riga. Il riscontro del
 *  salvataggio sta accanto alla riga, non solo nel toast in basso. */
function GroupsCell({
  groups,
  value,
  onChange,
  saveState,
  disabled,
}: {
  groups: GroupOut[];
  value: string[];
  onChange: (groupIds: string[]) => void;
  saveState: React.ComponentProps<typeof SaveIndicator>["state"];
  disabled: boolean;
}) {
  const selectedNames = groups.filter((g) => value.includes(g.id)).map((g) => g.name);

  return (
    <details>
      <summary className="group-summary">
        {selectedNames.length > 0 ? selectedNames.join(", ") : "Nessuno"}
      </summary>
      <div className="group-summary-editor">
        <GroupPicker groups={groups} value={value} onChange={onChange} disabled={disabled} />
        <SaveIndicator state={saveState} />
      </div>
    </details>
  );
}

function PendingInvitations() {
  const queryClient = useQueryClient();
  const { data: invitations, error } = useQuery<InvitationSummaryOut[], ApiError>({
    queryKey: ["invitations"],
    queryFn: () => apiGet<InvitationSummaryOut[]>("/api/v1/invitations"),
  });
  const { error: actionError, run } = useAction();
  const [revoking, setRevoking] = useState<InvitationSummaryOut | null>(null);

  async function revoke(invitation: InvitationSummaryOut) {
    // Il dialogo resta aperto (e occupato) fino alla risposta: chiuderlo prima
    // lasciava spazio a un secondo click, cioè a una seconda DELETE.
    await run(
      async () => {
        await apiDelete(`/api/v1/invitations/${invitation.id}`);
        await queryClient.invalidateQueries({ queryKey: ["invitations"] });
      },
      { success: `Invito a ${invitation.email} revocato.` },
    );
    setRevoking(null);
  }

  if (!invitations || invitations.length === 0) return null;

  return (
    <div className="card">
      <div className="card-header">
        <h3>Inviti in sospeso</h3>
      </div>
      {error && <ErrorBanner error={error} />}
      {actionError && <ErrorBanner error={actionError} />}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Ruolo</th>
              <th>Scade il</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {invitations.map((invitation) => (
              <tr key={invitation.id}>
                <td>{invitation.email}</td>
                <td>{roleLabel(invitation.role)}</td>
                <td>{formatDateTime(invitation.expires_at)}</td>
                <td>
                  <div className="row-actions">
                    <button className="danger" onClick={() => setRevoking(invitation)}>
                      Revoca
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {revoking && (
        <ConfirmDialog
          title={`Revoca l'invito a ${revoking.email}`}
          confirmLabel="Revoca invito"
          onConfirm={() => revoke(revoking)}
          onCancel={() => setRevoking(null)}
        >
          <p>Il collegamento già inviato smette di funzionare. Se ne può creare un altro.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}

function InviteForm({ roles }: { roles: UserRole[] }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [invitation, setInvitation] = useState<InvitationOut | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!email.includes("@")) {
      setEmailError("Indica un indirizzo email valido.");
      return;
    }
    setEmailError(null);
    setInvitation(null);
    const ok = await run(
      async () => {
        const result = await apiPost<InvitationOut>("/api/v1/invitations", { email, role });
        setInvitation(result);
        await queryClient.invalidateQueries({ queryKey: ["invitations"] });
      },
      { success: `Invito creato per ${email}.` },
    );
    if (ok) setEmail("");
  }

  return (
    <details className="card collapsible">
      <summary>Invita un membro</summary>
      <p className="card-hint">
        L'invito crea un collegamento a scadenza: chi lo apre sceglie la propria password e
        l'utenza nasce già con il ruolo indicato qui.
      </p>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
        <RequiredLegend />
        <Field id="invite-email" label="Email" required error={emailError}>
          <input
            {...fieldAria("invite-email", { error: emailError })}
            type="email"
            autoComplete="off"
            placeholder="email@esempio.it"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>
        <Field id="invite-role" label="Ruolo" hint={ROLE_HINTS[role]}>
          <select
            {...fieldAria("invite-role", { hint: true })}
            value={role}
            onChange={(event) => setRole(event.target.value as UserRole)}
          >
            {roles.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Invio…" : "Invita"}
          </button>
        </div>
      </form>
      {invitation && (
        <div className="card nested-card">
          <p className="card-hint">
            {invitation.email_sent
              ? "Email inviata all'indirizzo indicato."
              : "Email non inviata: distribuisci il link manualmente."}
          </p>
          <div className="copy-field">
            <code>{invitation.invite_url}</code>
            <CopyButton value={invitation.invite_url} label="Copia link" />
          </div>
        </div>
      )}
    </details>
  );
}

function CreateUserForm({ groups, roles }: { groups: GroupOut[]; roles: UserRole[] }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    // Le stesse due regole del backend, dette prima di spendere un giro di
    // rete e con il campo indicato invece di un 422 generico.
    const errors: { email?: string; password?: string } = {};
    if (!email.includes("@")) errors.email = "Indica un indirizzo email valido.";
    // In code point, come pydantic: con `.length` un'emoji conta due.
    if ([...password].length < MIN_PASSWORD_LENGTH)
      errors.password = `La password deve avere almeno ${MIN_PASSWORD_LENGTH} caratteri.`;
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const ok = await run(
      async () => {
        await apiPost<UserOut>("/api/v1/users", { email, password, role, group_ids: groupIds });
        await queryClient.invalidateQueries({ queryKey: ["users"] });
      },
      { success: `Utenza ${email} creata.` },
    );
    if (ok) {
      setEmail("");
      setPassword("");
      setGroupIds([]);
    }
  }

  return (
    <details className="card collapsible">
      <summary>Crea utenza</summary>
      <p className="card-hint">
        Utenza con password scelta da chi la crea: si usa quando non si vuole passare dall'invito.
      </p>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
        <RequiredLegend />
        <Field id="create-user-email" label="Email" required error={fieldErrors.email}>
          <input
            {...fieldAria("create-user-email", { error: fieldErrors.email })}
            type="email"
            autoComplete="off"
            placeholder="nuova-utenza@esempio.it"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>
        <Field
          id="create-user-password"
          label="Password"
          required
          error={fieldErrors.password}
          hint={`Almeno ${MIN_PASSWORD_LENGTH} caratteri.`}
        >
          <input
            {...fieldAria("create-user-password", { hint: true, error: fieldErrors.password })}
            type="password"
            autoComplete="new-password"
            placeholder="Password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>
        <Field id="create-user-role" label="Ruolo" hint={ROLE_HINTS[role]}>
          <select
            {...fieldAria("create-user-role", { hint: true })}
            value={role}
            onChange={(event) => setRole(event.target.value as UserRole)}
          >
            {roles.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        </Field>
        <Field
          id="create-user-groups"
          label="Gruppi di receiver da gestire"
          optional
          hint="Serve solo al ruolo Operatore: gli altri ruoli vedono comunque tutti i gruppi."
        >
          <div id="create-user-groups">
            <GroupPicker groups={groups} value={groupIds} onChange={setGroupIds} />
          </div>
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Creazione…" : "Crea"}
          </button>
        </div>
      </form>
    </details>
  );
}

export default function UsersPage() {
  const queryClient = useQueryClient();
  const {
    data: users,
    isLoading,
    error,
  } = useQuery<UserOut[], ApiError>({
    queryKey: ["users"],
    queryFn: () => apiGet<UserOut[]>("/api/v1/users"),
  });
  const { data: groups } = useQuery<GroupOut[], ApiError>({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });
  const { user: me, role: sessionRole, reloadProfile, logout } = useSession();
  const { busy, error: actionError, saveState, run } = useAction();
  const [removing, setRemoving] = useState<UserOut | null>(null);
  // Il proprio ruolo non si cambia con un solo gesto sulla tendina: si chiede
  // conferma, perché declassarsi toglie l'accesso a questa stessa pagina.
  const [selfRoleChange, setSelfRoleChange] = useState<UserRole | null>(null);
  // Quale campo ha salvato per ultimo: senza, l'esito "Salvato" comparirebbe
  // su tutte le righe insieme, perché lo stato dell'operazione è uno solo.
  const [lastSaved, setLastSaved] = useState<string | null>(null);
  // Gruppi richiesti e non ancora confermati dalla cache, per utenza.
  const [requestedGroups, setRequestedGroups] = useState<Record<string, string[]>>({});
  const roles = assignableRoles(sessionRole);

  /** Stato da mostrare accanto a un campo modificabile in linea. */
  function stateOf(key: string) {
    if (busy === key) return "saving" as const;
    if (lastSaved === key) return saveState;
    return "idle" as const;
  }

  function isSelf(user: UserOut): boolean {
    return me !== null && user.id === me.id;
  }

  /** Un owner lo modifica o lo rimuove solo un altro owner (il backend
   *  risponde 403 a un admin): per un admin la riga resta in sola lettura. */
  function canManage(user: UserOut): boolean {
    return sessionRole === "owner" || user.role !== "owner";
  }

  async function changeRole(user: UserOut, role: UserRole) {
    setLastSaved(`role:${user.id}`);
    const ok = await run(
      async () => {
        await apiPatch(`/api/v1/users/${user.id}`, { role });
        await queryClient.invalidateQueries({ queryKey: ["users"] });
      },
      { name: `role:${user.id}`, success: `${user.email} ora è ${roleLabel(role)}.` },
    );
    // Senza, la sessione continuerebbe a presentarsi col ruolo vecchio: menu,
    // pagine e pulsanti di chi non ha più quei permessi.
    if (ok && isSelf(user)) await reloadProfile();
  }

  function requestRoleChange(user: UserOut, role: UserRole) {
    if (isSelf(user)) setSelfRoleChange(role);
    else void changeRole(user, role);
  }

  async function changeGroups(user: UserOut, groupIds: string[]) {
    setLastSaved(`groups:${user.id}`);
    // La lista richiesta sta in stato finché il salvataggio non è finito e la
    // cache è riletta: il click successivo parte da lei, non da una lista in
    // cache che può non essere ancora ridisegnata.
    setRequestedGroups((current) => ({ ...current, [user.id]: groupIds }));
    const ok = await run(
      async () => {
        await apiPatch(`/api/v1/users/${user.id}`, { group_ids: groupIds });
        await queryClient.invalidateQueries({ queryKey: ["users"] });
      },
      { name: `groups:${user.id}`, success: `Gruppi di ${user.email} aggiornati.` },
    );
    setRequestedGroups((current) => {
      const next = { ...current };
      delete next[user.id];
      return next;
    });
    if (ok && isSelf(user)) await reloadProfile();
  }

  async function remove(user: UserOut) {
    const self = isSelf(user);
    const ok = await run(
      async () => {
        await apiDelete(`/api/v1/users/${user.id}`);
        if (!self) await queryClient.invalidateQueries({ queryKey: ["users"] });
      },
      { name: `remove:${user.id}`, success: `Utenza ${user.email} rimossa.` },
    );
    // Il dialogo si chiude a risposta arrivata: prima restava cliccabile e un
    // doppio click mandava due DELETE.
    setRemoving(null);
    // Chi ha rimosso se stesso non ha più una sessione valida: restare sulla
    // pagina vorrebbe dire una fila di 401 senza spiegazione.
    if (ok && self) await logout();
  }

  const lastOwnerConflict = actionError?.type === "/problems/last-owner";

  return (
    <div>
      <div className="page-header">
        <h1>Utenti</h1>
      </div>
      <p className="page-subtitle">
        Chi entra in questo tenant e cosa può fare. Il ruolo si cambia dalla riga: il salvataggio è
        immediato e viene confermato accanto al campo.
      </p>
      {error && <ErrorBanner error={error} />}
      {actionError && (
        <div className="error-banner" role="alert">
          {lastOwnerConflict
            ? "Non è possibile rimuovere o declassare l'ultimo owner del tenant."
            : actionError.detail || actionError.title}
        </div>
      )}

      <CreateUserForm groups={groups ?? []} roles={roles} />
      <InviteForm roles={roles} />
      <PendingInvitations />

      <div className="card">
        <div className="card-header">
          <h3>Utenze</h3>
        </div>
        {isLoading ? (
          <EmptyState message="Caricamento…" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Ruolo</th>
                  <th>Gruppi gestiti</th>
                  <th>Stato</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users?.map((user) => {
                  const manageable = canManage(user);
                  const readOnlyHint = manageable
                    ? undefined
                    : "Solo un owner può modificare o rimuovere un altro owner.";
                  return (
                    <tr key={user.id}>
                      <td>
                        {user.email}
                        {isSelf(user) && <span className="text-muted text-sm"> (tu)</span>}
                      </td>
                      <td>
                        <div className="status-cell">
                          <select
                            aria-label={`Ruolo di ${user.email}`}
                            value={user.role}
                            disabled={busy !== null || !manageable}
                            title={readOnlyHint}
                            onChange={(event) =>
                              requestRoleChange(user, event.target.value as UserRole)
                            }
                          >
                            {/* La riga di un owner in sola lettura deve comunque
                                poter mostrare "owner" come valore. */}
                            {(manageable ? roles : ROLES).map((r) => (
                              <option key={r} value={r}>
                                {roleLabel(r)}
                              </option>
                            ))}
                          </select>
                          <SaveIndicator state={stateOf(`role:${user.id}`)} />
                        </div>
                      </td>
                      <td>
                        <GroupsCell
                          groups={groups ?? []}
                          value={requestedGroups[user.id] ?? user.group_ids}
                          onChange={(groupIds) => void changeGroups(user, groupIds)}
                          saveState={stateOf(`groups:${user.id}`)}
                          disabled={busy !== null || !manageable}
                        />
                      </td>
                      <td>
                        <span
                          className={
                            user.status === "active" ? "status-pill ok" : "status-pill warn"
                          }
                        >
                          {userStatusLabel(user.status)}
                        </span>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="danger"
                            disabled={busy !== null || !manageable}
                            title={readOnlyHint}
                            onClick={() => setRemoving(user)}
                          >
                            Rimuovi
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {removing && (
        <ConfirmDialog
          title={isSelf(removing) ? "Rimuovi la tua utenza" : `Rimuovi ${removing.email}`}
          confirmLabel={isSelf(removing) ? "Rimuovi la mia utenza" : "Rimuovi utenza"}
          onConfirm={() => remove(removing)}
          onCancel={() => setRemoving(null)}
        >
          {isSelf(removing) ? (
            <p>
              Stai rimuovendo l'utenza con cui sei entrato: la sessione si chiude subito e non potrai
              più accedere a questo tenant.
            </p>
          ) : (
            <p>
              L'utenza perde subito l'accesso. Le notifiche che ha letto o verificato restano con il
              suo nome nell'audit.
            </p>
          )}
        </ConfirmDialog>
      )}

      {selfRoleChange && me && (
        <ConfirmDialog
          title="Cambia il tuo ruolo"
          confirmLabel={`Diventa ${roleLabel(selfRoleChange)}`}
          onConfirm={async () => {
            const self = users?.find((u) => u.id === me.id);
            if (self) await changeRole(self, selfRoleChange);
            setSelfRoleChange(null);
          }}
          onCancel={() => setSelfRoleChange(null)}
        >
          <p>
            {`Stai cambiando il tuo ruolo da ${roleLabel(me.role)} a ${roleLabel(selfRoleChange)}.`}
            {hasRole(selfRoleChange, ADMIN_ROLES)
              ? " I permessi cambiano da subito, e quelli che il nuovo ruolo non ha non potrai riprenderteli da solo."
              : " Perderai subito l'accesso a questa pagina, e per tornare indietro servirà un altro owner o admin."}
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
