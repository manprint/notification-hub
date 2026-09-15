import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "../api/client";
import type {
  ApiError,
  ReceiverOut,
  Severity,
  SeverityChainItemOut,
  SeverityReplayOut,
  SeverityRuleOut,
  TestSeverityOut,
} from "../api/types";
import ConfirmDialog from "./ConfirmDialog";
import ErrorBanner from "./ErrorBanner";
import Field, { fieldAria } from "./Field";
import SeverityBadge from "./SeverityBadge";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { formatDurationSeconds } from "../lib/duration";
import { formatDateTime } from "../lib/format";
import { MEMBER_ROLES, hasRole } from "../lib/roles";
import { severitySourceLabel } from "../lib/severitySource";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

// Etichette condivise con l'elenco e il dettaglio delle notifiche: la stessa
// origine non puo' chiamarsi in due modi diversi in due schermate.
const sourceLabel = severitySourceLabel;

/** Riassunto della catena con la configurazione reale di questo receiver: è la
 *  risposta alla domanda "chi decide la severity, e in che ordine". */
function SeverityChainSummary({
  receiver,
  activeRules,
}: {
  receiver: ReceiverOut;
  activeRules: number;
}) {
  return (
    <ol className="chain-list">
      <li>
        <strong>Severity esplicita</strong> — se chi invia passa <code>X-Severity</code> (o{" "}
        <code>?severity=</code>), vince quella e la catena si ferma.
      </li>
      <li>
        <strong>Exit code diverso da zero</strong> — con l'header <code>X-Exit-Code</code>:{" "}
        {receiver.exit_code_severity ? (
          <>
            diventa <SeverityBadge severity={receiver.exit_code_severity} />
          </>
        ) : (
          <em>nessun effetto (disattivato su questo receiver)</em>
        )}
      </li>
      <li>
        <strong>Durata oltre la soglia</strong> — con l'header <code>X-Duration-Ms</code>:{" "}
        {receiver.duration_threshold_seconds !== null && receiver.duration_severity !== null ? (
          <>
            oltre {formatDurationSeconds(receiver.duration_threshold_seconds)} diventa{" "}
            <SeverityBadge severity={receiver.duration_severity} />. Se scatta insieme all'exit code
            vince la severity più grave delle due.
          </>
        ) : (
          <em>nessun effetto (nessuna soglia su questo receiver)</em>
        )}
      </li>
      <li>
        <strong>Regole</strong> — prima quelle scritte qui sotto (
        {activeRules === 0 ? "nessuna attiva" : null}
        {activeRules === 1 ? "1 attiva" : null}
        {activeRules > 1 ? `${activeRules} attive` : null}), poi quelle dei preset applicati.
        Valutate dall'alto verso il basso sul contenuto <strong>intero</strong> del messaggio: la
        prima che corrisponde vince.
      </li>
      <li>
        <strong>Default del receiver</strong> — se nessuna regola corrisponde:{" "}
        <SeverityBadge severity={receiver.default_severity} />
      </li>
    </ol>
  );
}

function RuleForm({
  receiverId,
  rule,
  onDone,
}: {
  receiverId: string;
  rule?: SeverityRuleOut;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [pattern, setPattern] = useState(rule?.pattern ?? "");
  const [severity, setSeverity] = useState<Severity>(rule?.severity ?? "error");
  const [caseInsensitive, setCaseInsensitive] = useState(rule?.case_insensitive ?? true);
  const [patternError, setPatternError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (pattern.trim() === "") {
      setPatternError("Il pattern è obbligatorio.");
      return;
    }
    setPatternError(null);
    const body = { pattern, severity, case_insensitive: caseInsensitive };
    const ok = await run(
      async () => {
        if (rule) {
          await apiPatch(`/api/v1/severity-rules/${rule.id}`, body);
        } else {
          // Nessuna priorità: il backend accoda la regola in fondo. L'ordine si
          // cambia con le frecce, non indovinando un numero libero.
          await apiPost(`/api/v1/receivers/${receiverId}/severity-rules`, {
            ...body,
            enabled: true,
          });
        }
        await queryClient.invalidateQueries({ queryKey: ["severity-rules", receiverId] });
        await queryClient.invalidateQueries({ queryKey: ["severity-chain", receiverId] });
      },
      { success: rule ? "Regola aggiornata." : "Regola aggiunta in fondo alla catena." },
    );
    if (ok) {
      if (!rule) setPattern("");
      onDone();
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      {patternError && (
        <p className="field-error" role="alert">
          {patternError}
        </p>
      )}
      <div className="toolbar">
        <input
          aria-label="Pattern RE2"
          aria-invalid={patternError ? true : undefined}
          placeholder="Pattern RE2, es. ERRORE|FALL(ITO|IMENTO)"
          value={pattern}
          onChange={(event) => setPattern(event.target.value)}
          required
          maxLength={200}
          className="grow-input"
        />
        <select
          aria-label="Severity assegnata"
          value={severity}
          onChange={(event) => setSeverity(event.target.value as Severity)}
        >
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={caseInsensitive}
            onChange={(event) => setCaseInsensitive(event.target.checked)}
          />
          ignora maiuscole
        </label>
        <button type="submit" className="primary" disabled={busy !== null}>
          {rule ? "Salva" : "Aggiungi regola"}
        </button>
        {rule && (
          <button type="button" onClick={onDone}>
            Annulla
          </button>
        )}
      </div>
    </form>
  );
}

/** La catena effettiva: regole proprie e regole dei preset in un elenco solo,
 *  nell'ordine reale di valutazione. Con due o tre preset applicati, ricostruire
 *  a mente chi viene prima non è ragionevole. */
function EffectiveChain({ receiverId }: { receiverId: string }) {
  const { data, error } = useQuery<SeverityChainItemOut[], ApiError>({
    queryKey: ["severity-chain", receiverId],
    queryFn: () => apiGet<SeverityChainItemOut[]>(`/api/v1/receivers/${receiverId}/severity-chain`),
  });

  if (error) return <ErrorBanner error={error} />;
  if (!data || data.length === 0) {
    return (
      <p className="card-hint">
        Nessuna regola attiva: ogni notifica riceve la severity di default del receiver.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Pattern</th>
            <th>Severity</th>
            <th>Da dove arriva</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.rule_id}>
              <td>{item.position}</td>
              <td>
                <code>{item.pattern}</code>
              </td>
              <td>
                <SeverityBadge severity={item.severity} />
              </td>
              <td>
                {item.origin === "preset" ? (
                  <>
                    preset <strong>{item.preset_name}</strong>
                  </>
                ) : (
                  "regola di questo receiver"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReplayPanel({ receiverId }: { receiverId: string }) {
  const [open, setOpen] = useState(false);
  const { data, isFetching, error, refetch } = useQuery<SeverityReplayOut, ApiError>({
    queryKey: ["severity-replay", receiverId],
    queryFn: () => apiGet<SeverityReplayOut>(`/api/v1/receivers/${receiverId}/severity-rules/replay`),
    enabled: open,
  });

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}>Prova sulle ultime notifiche ricevute</button>
    );
  }

  return (
    <div>
      <div className="toolbar">
        <button onClick={() => void refetch()} disabled={isFetching}>
          {isFetching ? "Ricalcolo…" : "Ricalcola"}
        </button>
        <button onClick={() => setOpen(false)}>Chiudi</button>
      </div>
      {error && <ErrorBanner error={error} />}
      {data && data.items.length === 0 && (
        <p className="card-hint">Questo receiver non ha ancora ricevuto notifiche.</p>
      )}
      {data && data.items.length > 0 && (
        <>
          <p className="card-hint">
            {data.changed_count === 0
              ? "Con le regole attuali nessuna delle ultime notifiche cambierebbe severity."
              : `Con le regole attuali ${data.changed_count} delle ultime ${data.items.length} notifiche cambierebbero severity.`}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ricevuta</th>
                  <th>Anteprima</th>
                  <th>Severity registrata</th>
                  <th>Con le regole attuali</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.notification_id}>
                    <td>{formatDateTime(item.received_at)}</td>
                    <td className="cell-preview">
                      {item.content_preview}
                      {item.truncated && (
                        <div className="cell-diagnostics">
                          contenuto su object storage: rivalutata solo l'anteprima
                        </div>
                      )}
                    </td>
                    <td>
                      <SeverityBadge severity={item.stored_severity} />
                      <div className="cell-diagnostics">{sourceLabel(item.stored_source)}</div>
                    </td>
                    <td>
                      <SeverityBadge severity={item.replayed_severity} />
                      {item.changed && <span className="status-pill">cambia</span>}
                      <div className="cell-diagnostics">
                        {sourceLabel(item.replayed_source)}
                        {item.matched_preset_name && <> «{item.matched_preset_name}»</>}
                        {item.matched_pattern && (
                          <>
                            : <code>{item.matched_pattern}</code>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export default function SeverityRulesPanel({ receiver }: { receiver: ReceiverOut }) {
  const receiverId = receiver.id;
  const { role } = useSession();
  const canManage = hasRole(role, MEMBER_ROLES);
  const queryClient = useQueryClient();

  const { data: rules, error: rulesError } = useQuery<SeverityRuleOut[], ApiError>({
    queryKey: ["severity-rules", receiverId],
    queryFn: () => apiGet<SeverityRuleOut[]>(`/api/v1/receivers/${receiverId}/severity-rules`),
  });

  const { busy, error, run } = useAction();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingRule, setDeletingRule] = useState<SeverityRuleOut | null>(null);
  const [testContent, setTestContent] = useState("");
  const [testExitCode, setTestExitCode] = useState("");
  const [testDurationSeconds, setTestDurationSeconds] = useState("");
  const [testResult, setTestResult] = useState<TestSeverityOut | null>(null);
  const [testError, setTestError] = useState<ApiError | null>(null);

  const ordered = rules ?? [];
  const firstActiveId = ordered.find((r) => r.enabled)?.id;

  async function mutate(action: () => Promise<unknown>, success: string) {
    await run(async () => {
      await action();
      await queryClient.invalidateQueries({ queryKey: ["severity-rules", receiverId] });
      await queryClient.invalidateQueries({ queryKey: ["severity-chain", receiverId] });
      await queryClient.invalidateQueries({ queryKey: ["severity-replay", receiverId] });
    }, { success });
  }

  function move(index: number, delta: number) {
    const next = [...ordered];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    void mutate(
      () =>
        apiPut(`/api/v1/receivers/${receiverId}/severity-rules/order`, {
          rule_ids: next.map((r) => r.id),
        }),
      "Ordine delle regole aggiornato.",
    );
  }

  async function runTest(event: React.FormEvent) {
    event.preventDefault();
    setTestError(null);
    setTestResult(null);
    try {
      setTestResult(
        await apiPost<TestSeverityOut>(`/api/v1/receivers/${receiverId}/test-severity`, {
          content: testContent,
          exit_code: testExitCode === "" ? undefined : Number(testExitCode),
          // Il campo si compila in secondi, come la soglia; l'API ragiona in
          // millisecondi come l'header.
          duration_ms:
            testDurationSeconds === "" ? undefined : Math.round(Number(testDurationSeconds) * 1000),
        }),
      );
    } catch (err) {
      setTestError(err as ApiError);
    }
  }

  return (
    <>
      <div className="card">
        <div className="card-header">
          <h3>Come viene decisa la severity</h3>
        </div>
        <SeverityChainSummary receiver={receiver} activeRules={ordered.filter((r) => r.enabled).length} />
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Regole di severity</h3>
        </div>
        <p className="card-hint">
          Valutate nell'ordine in cui compaiono qui: <strong>la prima che corrisponde vince</strong> e
          ferma la catena. Il pattern è un'espressione regolare RE2 (niente lookahead né
          backreference) e viene cercata in qualsiasi punto del messaggio, senza limiti di lunghezza.
        </p>
        {rulesError && <ErrorBanner error={rulesError} />}
        {error && <ErrorBanner error={error} />}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ordine</th>
                <th>Pattern</th>
                <th>Severity</th>
                <th>Maiuscole</th>
                <th>Stato</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((rule, index) =>
                editingId === rule.id ? (
                  <tr key={rule.id}>
                    <td colSpan={6}>
                      <RuleForm
                        receiverId={receiverId}
                        rule={rule}
                        onDone={() => setEditingId(null)}
                      />
                    </td>
                  </tr>
                ) : (
                  <tr key={rule.id} className={rule.enabled ? undefined : "row-disabled"}>
                    <td>
                      <div className="row-actions">
                        <span>{index + 1}</span>
                        {canManage && (
                          <>
                            <button
                              aria-label={`Sposta su ${rule.pattern}`}
                              disabled={index === 0}
                              onClick={() => move(index, -1)}
                            >
                              ↑
                            </button>
                            <button
                              aria-label={`Sposta giù ${rule.pattern}`}
                              disabled={index === ordered.length - 1}
                              onClick={() => move(index, 1)}
                            >
                              ↓
                            </button>
                          </>
                        )}
                      </div>
                      {rule.id === firstActiveId && (
                        <div className="cell-diagnostics">valutata per prima</div>
                      )}
                    </td>
                    <td>
                      <code>{rule.pattern}</code>
                    </td>
                    <td>
                      <SeverityBadge severity={rule.severity} />
                    </td>
                    <td>{rule.case_insensitive ? "ignorate" : "distinte"}</td>
                    <td>
                      {canManage ? (
                        <label className="inline-check">
                          <input
                            type="checkbox"
                            checked={rule.enabled}
                            aria-label={`Attiva ${rule.pattern}`}
                            onChange={() =>
                              void mutate(
                                () =>
                                  apiPatch(`/api/v1/severity-rules/${rule.id}`, {
                                    enabled: !rule.enabled,
                                  }),
                                rule.enabled ? "Regola disattivata." : "Regola attivata.",
                              )
                            }
                          />
                          {rule.enabled ? "attiva" : "disattivata"}
                        </label>
                      ) : (
                        <span>{rule.enabled ? "attiva" : "disattivata"}</span>
                      )}
                    </td>
                    <td>
                      {canManage && (
                        <div className="row-actions">
                          <button disabled={busy !== null} onClick={() => setEditingId(rule.id)}>
                            Modifica
                          </button>
                          <button
                            className="danger"
                            disabled={busy !== null}
                            onClick={() => setDeletingRule(rule)}
                          >
                            Elimina
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
        {ordered.length === 0 && (
          <p className="card-hint">
            Nessuna regola: ogni notifica riceve la severity di default del receiver (
            {receiver.default_severity}).
          </p>
        )}

        {canManage && (
          <>
            <h4>Nuova regola</h4>
            <RuleForm receiverId={receiverId} onDone={() => undefined} />
          </>
        )}
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Catena effettiva</h3>
        </div>
        <p className="card-hint">
          Tutte le regole attive di questo receiver, proprie e dei preset, nell'ordine esatto in cui
          vengono provate.
        </p>
        <EffectiveChain receiverId={receiverId} />
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Prova severity</h3>
        </div>
        <p className="card-hint">
          Verifica la catena su un testo di esempio senza scrivere nessuna notifica.
        </p>
        {testError && <ErrorBanner error={testError} />}
        <form onSubmit={(event) => void runTest(event)}>
          <Field
            id="test-content"
            label="Contenuto di prova"
            wide
            hint="Il testo che arriverebbe dal job: le regole si applicano a tutto il messaggio."
          >
            <textarea
              {...fieldAria("test-content", { hint: true })}
              rows={4}
              value={testContent}
              onChange={(event) => setTestContent(event.target.value)}
            />
          </Field>
          <div className="form-grid">
            <Field
              id="test-exit-code"
              label="Exit code simulato"
              optional
              hint="Vuoto = nessun exit code."
            >
              <input
                {...fieldAria("test-exit-code", { hint: true })}
                type="number"
                value={testExitCode}
                onChange={(event) => setTestExitCode(event.target.value)}
              />
            </Field>
            <Field
              id="test-duration"
              label="Durata simulata in secondi"
              optional
              hint="Vuoto = nessuna durata."
            >
              <input
                {...fieldAria("test-duration", { hint: true })}
                type="number"
                min={0}
                value={testDurationSeconds}
                onChange={(event) => setTestDurationSeconds(event.target.value)}
              />
            </Field>
          </div>
          <div className="form-actions">
            <button type="submit">Esegui prova</button>
          </div>
        </form>
        {testResult && (
          <p>
            Severity risolta: <SeverityBadge severity={testResult.severity} /> — decisa da{" "}
            <strong>{sourceLabel(testResult.source)}</strong>
            {testResult.matched_preset_name && <> «{testResult.matched_preset_name}»</>}
            {testResult.matched_pattern && (
              <>
                {" "}
                (<code>{testResult.matched_pattern}</code>)
              </>
            )}
            {testResult.duration_exceeded && testResult.source !== "duration" && (
              <> — la soglia di durata è comunque superata</>
            )}
          </p>
        )}

        <h4>Prova sui messaggi già arrivati</h4>
        <p className="card-hint">
          Rivaluta le ultime notifiche di questo receiver con le regole attuali e mostra quali
          cambierebbero severity.
        </p>
        <ReplayPanel receiverId={receiverId} />
      </div>

      {deletingRule && (
        <ConfirmDialog
          title="Elimina questa regola"
          confirmLabel="Elimina regola"
          onConfirm={() => {
            const rule = deletingRule;
            setDeletingRule(null);
            void mutate(
              () => apiDelete(`/api/v1/severity-rules/${rule.id}`),
              "Regola eliminata.",
            );
          }}
          onCancel={() => setDeletingRule(null)}
        >
          <p>
            Le notifiche già ricevute non cambiano severity: la regola smette di valere da adesso.
          </p>
          <p>
            <code>{deletingRule.pattern}</code>
          </p>
        </ConfirmDialog>
      )}
    </>
  );
}
