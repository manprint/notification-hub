import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type { ApiError, InvitationOut, InvitationSummaryOut, UserOut, UserRole } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";

const ROLES: UserRole[] = ["owner", "admin", "member", "viewer"];

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
      <form onSubmit={(event) => void handleSubmit(event)}>
        <div className="toolbar">
          <input
            type="email"
            placeholder="email@esempio.it"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <select value={role} onChange={(event) => setRole(event.target.value as UserRole)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
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

export default function UsersPage() {
  const queryClient = useQueryClient();
  const { data: users, error } = useQuery<UserOut[], ApiError>({
    queryKey: ["users"],
    queryFn: () => apiGet<UserOut[]>("/api/v1/users"),
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

      <InviteForm />
      <PendingInvitations />

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Ruolo</th>
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
  );
}
