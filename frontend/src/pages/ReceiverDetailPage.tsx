import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiDelete, apiGet, apiPost } from "../api/client";
import type { ApiError, ReceiverOut, Severity, SeverityRuleOut, TestSeverityOut } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";
import { useSession } from "../hooks/useSession";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];
const ROTATE_ALLOWED_ROLES = ["owner", "admin"];

function SeverityRulesPanel({ receiverId }: { receiverId: string }) {
  const queryClient = useQueryClient();
  const { data: rules } = useQuery({
    queryKey: ["severity-rules", receiverId],
    queryFn: () => apiGet<SeverityRuleOut[]>(`/api/v1/receivers/${receiverId}/severity-rules`),
  });

  const [pattern, setPattern] = useState("");
  const [severity, setSeverity] = useState<Severity>("error");
  const [priority, setPriority] = useState(1);
  const [error, setError] = useState<ApiError | null>(null);

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
          {rules?.map((rule) => (
            <tr key={rule.id}>
              <td>{rule.priority}</td>
              <td>
                <code>{rule.pattern}</code>
              </td>
              <td>{rule.severity}</td>
              <td>
                <button onClick={() => void deleteRule(rule.id)}>Elimina</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

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

export default function ReceiverDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { role } = useSession();
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);
  const [rotateError, setRotateError] = useState<ApiError | null>(null);

  const { data: receiver, isLoading, error } = useQuery<ReceiverOut, ApiError>({
    queryKey: ["receiver", id],
    queryFn: () => apiGet<ReceiverOut>(`/api/v1/receivers/${id}`),
    enabled: Boolean(id),
  });

  if (isLoading) return <p>Caricamento…</p>;
  if (error) return <ErrorBanner error={error} />;
  if (!receiver) return null;

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
        <p>
          Slug: <code>{receiver.slug}</code>{" "}
          <button onClick={() => void copySlug()}>{copied ? "Copiato!" : "Copia"}</button>
        </p>
        <p>
          <code>{curlCommand}</code>
        </p>
        <p>Stato: {receiver.status}</p>
        <p>Limite corpo: {receiver.max_body_bytes} byte</p>
        <p>Rate limit: {receiver.rate_limit_per_min}/min</p>
        {receiver.status === "disabled" && (
          <div className="error-banner">
            {(receiver.rejected_last_24h ?? 0)} richieste rifiutate nelle ultime 24 ore.
          </div>
        )}
        {role !== null && ROTATE_ALLOWED_ROLES.includes(role) && (
          <button onClick={() => void doRotate()}>Rigenera slug</button>
        )}
      </div>

      <SeverityRulesPanel receiverId={receiver.id} />
    </div>
  );
}
