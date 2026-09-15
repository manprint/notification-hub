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
import ErrorBanner from "../components/ErrorBanner";

const ROLES: UserRole[] = ["owner", "admin", "member", "viewer"];

function GroupPicker({
  groups,
  value,
  onChange,
}: {
  groups: GroupOut[];
  value: string[];
  onChange: (groupIds: string[]) => void;
}) {
  function toggle(groupId: string, checked: boolean) {
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
            onChange={(event) => toggle(g.id, event.target.checked)}
          />
          {g.name}
        </label>
      ))}
    </div>
  );
}

function GroupsCell({
  groups,
  value,
  onChange,
}: {
  groups: GroupOut[];
  value: string[];
  onChange: (groupIds: string[]) => void;
}) {
  const selectedNames = groups.filter((g) => value.includes(g.id)).map((g) => g.name);

  return (
    <details>
      <summary className="group-summary">
        {selectedNames.length > 0 ? selectedNames.join(", ") : "Nessuno"}
      </summary>
      <div className="group-summary-editor">
        <GroupPicker groups={groups} value={value} onChange={onChange} />
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
  const [actionError, setActionError] = useState<ApiError | null>(null);

  async function revoke(id: string) {
    setActionError(null);
    try {
      await apiDelete(`/api/v1/invitations/${id}`);
      await queryClient.invalidateQueries({ queryKey: ["invitations"] });
    } catch (err) {
      setActionError(err as ApiError);
    }
  }

  if (!invitations || invitations.length === 0) return null;

  return (
    <div className="card">
      <h3>Inviti in sospeso</h3>
      {error && <ErrorBanner error={error} />}
      {actionError && <ErrorBanner error={actionError} />}
      <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Email</th>
            <th>Ruolo</th>
            <th>Scadenza</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {invitations.map((invitation) => (
            <tr key={invitation.id}>
              <td>{invitation.email}</td>
              <td>{invitation.role}</td>
              <td>{invitation.expires_at}</td>
              <td>
                <button onClick={() => void revoke(invitation.id)}>Revoca</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function InviteForm() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [invitation, setInvitation] = useState<InvitationOut | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setInvitation(null);
    try {
      const result = await apiPost<InvitationOut>("/api/v1/invitations", { email, role });
      setInvitation(result);
      setEmail("");
      await queryClient.invalidateQueries({ queryKey: ["invitations"] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  async function copyLink() {
    if (!invitation) return;
    await navigator.clipboard.writeText(invitation.invite_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="card">
      <h3>Invita un membro</h3>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-row">
          <label htmlFor="invite-email">Email</label>
          <input
            id="invite-email"
            type="email"
            placeholder="email@esempio.it"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="invite-role">Ruolo</label>
          <select
            id="invite-role"
            value={role}
            onChange={(event) => setRole(event.target.value as UserRole)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="form-actions">
          <button type="submit" className="primary">
            Invita
          </button>
        </div>
      </form>
      {invitation && (
        <div>
          <p>{invitation.email_sent ? "Email inviata." : "Email non inviata: distribuisci il link manualmente."}</p>
          <button onClick={() => void copyLink()}>{copied ? "Copiato!" : "Copia link"}</button>
        </div>
      )}
    </div>
  );
}

function CreateUserForm({ groups }: { groups: GroupOut[] }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPost<UserOut>("/api/v1/users", { email, password, role, group_ids: groupIds });
      setEmail("");
      setPassword("");
      setGroupIds([]);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <div className="card">
      <h3>Crea utenza</h3>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-row">
          <label htmlFor="create-user-email">Email</label>
          <input
            id="create-user-email"
            type="email"
            placeholder="nuova-utenza@esempio.it"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="create-user-password">Password</label>
          <input
            id="create-user-password"
            type="password"
            placeholder="Password"
            required
            minLength={12}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <span className="field-hint">Almeno 12 caratteri.</span>
        </div>
        <div className="form-row">
          <label htmlFor="create-user-role">Ruolo</label>
          <select
            id="create-user-role"
            value={role}
            onChange={(event) => setRole(event.target.value as UserRole)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label>Gruppi di receiver da gestire</label>
          <GroupPicker groups={groups} value={groupIds} onChange={setGroupIds} />
        </div>
        <div className="form-actions">
          <button type="submit" className="primary">
            Crea
          </button>
        </div>
      </form>
    </div>
  );
}

export default function UsersPage() {
  const queryClient = useQueryClient();
  const { data: users, error } = useQuery<UserOut[], ApiError>({
    queryKey: ["users"],
    queryFn: () => apiGet<UserOut[]>("/api/v1/users"),
  });
  const { data: groups } = useQuery<GroupOut[], ApiError>({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });
  const [actionError, setActionError] = useState<ApiError | null>(null);

  async function changeRole(userId: string, role: UserRole) {
    setActionError(null);
    try {
      await apiPatch(`/api/v1/users/${userId}`, { role });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch (err) {
      setActionError(err as ApiError);
    }
  }

  async function changeGroups(userId: string, groupIds: string[]) {
    setActionError(null);
    try {
      await apiPatch(`/api/v1/users/${userId}`, { group_ids: groupIds });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch (err) {
      setActionError(err as ApiError);
    }
  }

  async function remove(userId: string) {
    setActionError(null);
    try {
      await apiDelete(`/api/v1/users/${userId}`);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch (err) {
      setActionError(err as ApiError);
    }
  }

  const lastOwnerConflict = actionError?.type === "/problems/last-owner";

  return (
    <div>
      <h1>Utenti</h1>
      {error && <ErrorBanner error={error} />}
      {actionError && (
        <div className="error-banner">
          {lastOwnerConflict
            ? "Non è possibile rimuovere o declassare l'ultimo owner del tenant."
            : actionError.detail}
        </div>
      )}

      <CreateUserForm groups={groups ?? []} />
      <InviteForm />
      <PendingInvitations />

      <div className="card">
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
            {users?.map((user) => (
              <tr key={user.id}>
                <td>{user.email}</td>
                <td>
                  <select
                    value={user.role}
                    onChange={(event) => void changeRole(user.id, event.target.value as UserRole)}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <GroupsCell
                    groups={groups ?? []}
                    value={user.group_ids}
                    onChange={(groupIds) => void changeGroups(user.id, groupIds)}
                  />
                </td>
                <td>{user.status}</td>
                <td>
                  <button onClick={() => void remove(user.id)}>Rimuovi</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  );
}
