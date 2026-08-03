import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type { ApiError, ReceiverOut, Severity } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorBanner from "../components/ErrorBanner";
import ReceiverPresetsPanel from "../components/ReceiverPresetsPanel";
import SeverityRulesPanel from "../components/SeverityRulesPanel";
import { useSession } from "../hooks/useSession";
import { ADMIN_ROLES, MEMBER_ROLES, hasRole } from "../lib/roles";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];
const EXIT_CODE_DISABLED = "";

function EditReceiverForm({ receiver, onDone }: { receiver: ReceiverOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(receiver.name);
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>(receiver.default_severity);
  const [maxBodyBytes, setMaxBodyBytes] = useState(receiver.max_body_bytes);
  const [rateLimitPerMin, setRateLimitPerMin] = useState(receiver.rate_limit_per_min);
  const [exitCodeSeverity, setExitCodeSeverity] = useState<string>(
    receiver.exit_code_severity ?? EXIT_CODE_DISABLED,
  );
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPatch(`/api/v1/receivers/${receiver.id}`, {
        name,
        default_severity: defaultSeverity,
        max_body_bytes: maxBodyBytes,
        rate_limit_per_min: rateLimitPerMin,
        // null e' un valore, non "campo assente": disattiva la politica.
        exit_code_severity: exitCodeSeverity === EXIT_CODE_DISABLED ? null : exitCodeSeverity,
      });
      await queryClient.invalidateQueries({ queryKey: ["receiver", receiver.id] });
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <div className="form-row">
        <label htmlFor="receiver-edit-name">Nome</label>
        <input
          id="receiver-edit-name"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor="receiver-edit-severity">Severity di default</label>
        <select
          id="receiver-edit-severity"
          value={defaultSeverity}
          onChange={(event) => setDefaultSeverity(event.target.value as Severity)}
        >
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="receiver-edit-exit-code">Severity per exit code diverso da zero</label>
        <select
          id="receiver-edit-exit-code"
          value={exitCodeSeverity}
          onChange={(event) => setExitCodeSeverity(event.target.value)}
        >
          <option value={EXIT_CODE_DISABLED}>nessun effetto</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="receiver-edit-body">Limite corpo (byte)</label>
        <input
          id="receiver-edit-body"
          type="number"
          min={1}
          value={maxBodyBytes}
          onChange={(event) => setMaxBodyBytes(Number(event.target.value))}
        />
      </div>
      <div className="form-row">
        <label htmlFor="receiver-edit-rate">Rate limit (al minuto)</label>
        <input
          id="receiver-edit-rate"
          type="number"
          min={0}
          value={rateLimitPerMin}
          onChange={(event) => setRateLimitPerMin(Number(event.target.value))}
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

function DeleteReceiverButton({ receiver }: { receiver: ReceiverOut }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const navigate = useNavigate();

  async function confirmDelete() {
    try {
      await apiDelete(`/api/v1/receivers/${receiver.id}`);
      navigate("/groups");
    } catch (err) {
      setError(err as ApiError);
      setOpen(false);
    }
  }

  return (
    <div>
      {error && <ErrorBanner error={error} />}
      {open ? (
        <ConfirmDialog
          title={`Elimina receiver "${receiver.name}"`}
          expectedText={receiver.name}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setOpen(false)}
        >
          <p>Verranno eliminate anche le notifiche e le consegne collegate a questo receiver.</p>
        </ConfirmDialog>
      ) : (
        <button onClick={() => setOpen(true)}>Elimina receiver</button>
      )}
    </div>
  );
}

export default function ReceiverDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { role } = useSession();
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);
  const [rotateError, setRotateError] = useState<ApiError | null>(null);
  const [editing, setEditing] = useState(false);

  const { data: receiver, isLoading, error } = useQuery<ReceiverOut, ApiError>({
    queryKey: ["receiver", id],
    queryFn: () => apiGet<ReceiverOut>(`/api/v1/receivers/${id}`),
    enabled: Boolean(id),
  });

  if (isLoading) return <p>Caricamento…</p>;
  if (error) return <ErrorBanner error={error} />;
  if (!receiver) return null;

  const canManage = hasRole(role, MEMBER_ROLES);
  const curlCommand = `curl --data "corpo del messaggio" ${window.location.origin}/ingest/${receiver.slug}`;

  async function copySlug() {
    await navigator.clipboard.writeText(receiver!.slug);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function doRotate() {
    setRotateError(null);
    try {
      await apiPost(`/api/v1/receivers/${id}/rotate-slug`);
      await queryClient.invalidateQueries({ queryKey: ["receiver", id] });
    } catch (err) {
      setRotateError(err as ApiError);
    }
  }

  return (
    <div>
      <h1>{receiver.name}</h1>
      {rotateError && <ErrorBanner error={rotateError} />}

      <div className="card">
        {editing ? (
          <EditReceiverForm receiver={receiver} onDone={() => setEditing(false)} />
        ) : (
          <>
            <p>
              Slug: <code>{receiver.slug}</code>{" "}
              <button onClick={() => void copySlug()}>{copied ? "Copiato!" : "Copia"}</button>
            </p>
            <p>
              <code>{curlCommand}</code>
            </p>
            <p>Stato: {receiver.status}</p>
            <p>Severity di default: {receiver.default_severity}</p>
            <p>
              Severity per exit code diverso da zero:{" "}
              {receiver.exit_code_severity ?? "nessun effetto"}
            </p>
            <p>Limite corpo: {receiver.max_body_bytes} byte</p>
            <p>Rate limit: {receiver.rate_limit_per_min}/min</p>
            {receiver.status === "disabled" && (
              <div className="error-banner">
                {(receiver.rejected_last_24h ?? 0)} richieste rifiutate nelle ultime 24 ore.
              </div>
            )}
            <div className="toolbar">
              {hasRole(role, ADMIN_ROLES) && <button onClick={() => void doRotate()}>Rigenera slug</button>}
              {canManage && <button onClick={() => setEditing(true)}>Modifica receiver</button>}
              {canManage && <DeleteReceiverButton receiver={receiver} />}
            </div>
          </>
        )}
      </div>

      <ReceiverPresetsPanel receiverId={receiver.id} />
      <SeverityRulesPanel receiver={receiver} />
    </div>
  );
}
