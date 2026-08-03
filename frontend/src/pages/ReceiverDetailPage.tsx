import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type { ApiError, ReceiverOut, Severity, SeverityRuleOut, TestSeverityOut } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorBanner from "../components/ErrorBanner";
import { useSession } from "../hooks/useSession";
import { ADMIN_ROLES, MEMBER_ROLES, hasRole } from "../lib/roles";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

function EditSeverityRuleForm({
  rule,
  receiverId,
  onDone,
}: {
  rule: SeverityRuleOut;
  receiverId: string;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [pattern, setPattern] = useState(rule.pattern);
  const [severity, setSeverity] = useState<Severity>(rule.severity);
  const [priority, setPriority] = useState(rule.priority);
  const [caseInsensitive, setCaseInsensitive] = useState(rule.case_insensitive);
  const [enabled, setEnabled] = useState(rule.enabled);
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPatch(`/api/v1/severity-rules/${rule.id}`, {
        pattern,
        severity,
        priority,
        case_insensitive: caseInsensitive,
        enabled,
      });
      await queryClient.invalidateQueries({ queryKey: ["severity-rules", receiverId] });
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <tr>
      <td colSpan={4}>
        <form onSubmit={(event) => void handleSubmit(event)}>
          {error && <ErrorBanner error={error} />}
          <div className="toolbar">
            <input value={pattern} onChange={(event) => setPattern(event.target.value)} required />
            <select value={severity} onChange={(event) => setSeverity(event.target.value as Severity)}>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <input
              type="number"
              value={priority}
              onChange={(event) => setPriority(Number(event.target.value))}
            />
            <label>
              <input
                type="checkbox"
                checked={caseInsensitive}
                onChange={(event) => setCaseInsensitive(event.target.checked)}
              />
              case-insensitive
            </label>
            <label>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              attiva
            </label>
            <button type="submit" className="primary">
              Salva
            </button>
            <button type="button" onClick={onDone}>
              Annulla
            </button>
          </div>
        </form>
      </td>
    </tr>
  );
}

function SeverityRulesPanel({ receiverId }: { receiverId: string }) {
  const { role } = useSession();
  const canManage = hasRole(role, MEMBER_ROLES);
  const queryClient = useQueryClient();
  const { data: rules } = useQuery({
    queryKey: ["severity-rules", receiverId],
    queryFn: () => apiGet<SeverityRuleOut[]>(`/api/v1/receivers/${receiverId}/severity-rules`),
  });

  const [pattern, setPattern] = useState("");
  const [severity, setSeverity] = useState<Severity>("error");
  const [priority, setPriority] = useState(1);
  const [error, setError] = useState<ApiError | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const [testContent, setTestContent] = useState("");
  const [testResult, setTestResult] = useState<TestSeverityOut | null>(null);
  const [testError, setTestError] = useState<ApiError | null>(null);

  async function createRule(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPost(`/api/v1/receivers/${receiverId}/severity-rules`, {
        pattern,
        severity,
        priority,
        case_insensitive: true,
        enabled: true,
      });
      setPattern("");
      await queryClient.invalidateQueries({ queryKey: ["severity-rules", receiverId] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  async function deleteRule(id: string) {
    await apiDelete(`/api/v1/severity-rules/${id}`);
    await queryClient.invalidateQueries({ queryKey: ["severity-rules", receiverId] });
  }

  async function runTest(event: React.FormEvent) {
    event.preventDefault();
    setTestError(null);
    setTestResult(null);
    try {
      const result = await apiPost<TestSeverityOut>(`/api/v1/receivers/${receiverId}/test-severity`, {
        content: testContent,
      });
      setTestResult(result);
    } catch (err) {
      setTestError(err as ApiError);
    }
  }

  return (
    <div className="card">
      <h3>Regole di severity</h3>
      {error && <ErrorBanner error={error} />}
      <table>
        <thead>
          <tr>
            <th>Priorità</th>
            <th>Pattern</th>
            <th>Severity</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rules?.map((rule) =>
            editingId === rule.id ? (
              <EditSeverityRuleForm
                key={rule.id}
                rule={rule}
                receiverId={receiverId}
                onDone={() => setEditingId(null)}
              />
            ) : (
              <tr key={rule.id}>
                <td>{rule.priority}</td>
                <td>
                  <code>{rule.pattern}</code>
                </td>
                <td>{rule.severity}</td>
                <td>
                  {canManage && (
                    <>
                      <button onClick={() => setEditingId(rule.id)}>Modifica</button>
                      <button onClick={() => void deleteRule(rule.id)}>Elimina</button>
                    </>
                  )}
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>

      {canManage && (
        <form onSubmit={(event) => void createRule(event)}>
          <div className="toolbar">
            <input
              placeholder="Pattern RE2"
              value={pattern}
              onChange={(event) => setPattern(event.target.value)}
              required
            />
            <select value={severity} onChange={(event) => setSeverity(event.target.value as Severity)}>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <input
              type="number"
              value={priority}
              onChange={(event) => setPriority(Number(event.target.value))}
            />
            <button type="submit" className="primary">
              Aggiungi regola
            </button>
          </div>
        </form>
      )}

      <h3>Prova severity</h3>
      {testError && <ErrorBanner error={testError} />}
      <form onSubmit={(event) => void runTest(event)}>
        <div className="form-row">
          <label htmlFor="test-content">Contenuto di prova</label>
          <textarea
            id="test-content"
            value={testContent}
            onChange={(event) => setTestContent(event.target.value)}
          />
        </div>
        <button type="submit">Esegui prova</button>
      </form>
      {testResult && (
        <p>
          Severity risolta: <strong>{testResult.severity}</strong> (fonte: {testResult.source}
          {testResult.matched_pattern && (
            <>
              , regola <code>{testResult.matched_pattern}</code>
            </>
          )}
          )
        </p>
      )}
    </div>
  );
}

function EditReceiverForm({ receiver, onDone }: { receiver: ReceiverOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(receiver.name);
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>(receiver.default_severity);
  const [maxBodyBytes, setMaxBodyBytes] = useState(receiver.max_body_bytes);
  const [rateLimitPerMin, setRateLimitPerMin] = useState(receiver.rate_limit_per_min);
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

      <SeverityRulesPanel receiverId={receiver.id} />
    </div>
  );
}
