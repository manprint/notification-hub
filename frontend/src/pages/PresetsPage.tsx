import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "../api/client";
import type {
  ApiError,
  BuiltinPresetOut,
  Severity,
  SeverityPresetDetailOut,
  SeverityPresetOut,
  SeverityPresetRuleOut,
  SyncBuiltinPresetsOut,
} from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import SeverityBadge from "../components/SeverityBadge";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { ADMIN_ROLES, hasRole } from "../lib/roles";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

function PresetRuleForm({
  presetId,
  rule,
  onDone,
}: {
  presetId: string;
  rule?: SeverityPresetRuleOut;
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
          await apiPatch(`/api/v1/severity-preset-rules/${rule.id}`, body);
        } else {
          // Nessuna priorità: il backend accoda. L'ordine si cambia con le frecce.
          await apiPost(`/api/v1/severity-presets/${presetId}/rules`, { ...body, enabled: true });
        }
        await queryClient.invalidateQueries({ queryKey: ["preset", presetId] });
        await queryClient.invalidateQueries({ queryKey: ["presets"] });
      },
      { success: rule ? "Regola del preset aggiornata." : "Regola aggiunta al preset." },
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
          aria-label="Pattern RE2 del preset"
          aria-invalid={patternError ? true : undefined}
          placeholder="Pattern RE2, es. No space left on device"
          value={pattern}
          onChange={(event) => setPattern(event.target.value)}
          required
          maxLength={200}
          className="grow-input"
        />
        <select
          aria-label="Severity della regola del preset"
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

function PresetRules({ presetId, canManage }: { presetId: string; canManage: boolean }) {
  const queryClient = useQueryClient();
  const { busy, error, run } = useAction();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingRule, setDeletingRule] = useState<SeverityPresetRuleOut | null>(null);

  const { data, error: loadError } = useQuery<SeverityPresetDetailOut, ApiError>({
    queryKey: ["preset", presetId],
    queryFn: () => apiGet<SeverityPresetDetailOut>(`/api/v1/severity-presets/${presetId}`),
  });

  const rules = data?.rules ?? [];

  async function mutate(action: () => Promise<unknown>, success: string) {
    await run(async () => {
      await action();
      await queryClient.invalidateQueries({ queryKey: ["preset", presetId] });
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
    }, { success });
  }

  function move(index: number, delta: number) {
    const next = [...rules];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    void mutate(
      () =>
        apiPut(`/api/v1/severity-presets/${presetId}/rules/order`, {
          rule_ids: next.map((r) => r.id),
        }),
      "Ordine delle regole aggiornato.",
    );
  }

  return (
    <div>
      {loadError && <ErrorBanner error={loadError} />}
      {error && <ErrorBanner error={error} />}

      {rules.length === 0 ? (
        <p className="card-hint">Questo preset non ha ancora regole.</p>
      ) : (
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
              {rules.map((rule, index) =>
                editingId === rule.id ? (
                  <tr key={rule.id}>
                    <td colSpan={6}>
                      <PresetRuleForm
                        presetId={presetId}
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
                              disabled={index === rules.length - 1}
                              onClick={() => move(index, 1)}
                            >
                              ↓
                            </button>
                          </>
                        )}
                      </div>
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
                                  apiPatch(`/api/v1/severity-preset-rules/${rule.id}`, {
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
      )}

      {canManage && (
        <>
          <h4>Nuova regola</h4>
          <PresetRuleForm presetId={presetId} onDone={() => undefined} />
        </>
      )}

      {deletingRule && (
        <ConfirmDialog
          title="Elimina questa regola del preset"
          confirmLabel="Elimina regola"
          onConfirm={() => {
            const rule = deletingRule;
            setDeletingRule(null);
            void mutate(
              () => apiDelete(`/api/v1/severity-preset-rules/${rule.id}`),
              "Regola eliminata dal preset.",
            );
          }}
          onCancel={() => setDeletingRule(null)}
        >
          <p>
            La regola sparisce da <strong>tutti</strong> i receiver che usano questo preset.
          </p>
          <p>
            <code>{deletingRule.pattern}</code>
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}

function PresetCard({ preset, canManage }: { preset: SeverityPresetOut; canManage: boolean }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(preset.name);
  const [description, setDescription] = useState(preset.description);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { busy, error, run } = useAction();

  async function mutate(action: () => Promise<unknown>, success: string): Promise<boolean> {
    return run(async () => {
      await action();
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
      await queryClient.invalidateQueries({ queryKey: ["preset", preset.id] });
      await queryClient.invalidateQueries({ queryKey: ["presets-catalog"] });
    }, { success });
  }

  async function saveRename(event: React.FormEvent) {
    event.preventDefault();
    // Il modulo resta aperto se il salvataggio fallisce (nome duplicato → 409):
    // chiuderlo comunque farebbe sparire il testo insieme all'errore.
    const ok = await mutate(
      () => apiPatch(`/api/v1/severity-presets/${preset.id}`, { name, description }),
      "Preset rinominato.",
    );
    if (ok) setRenaming(false);
  }

  return (
    <div className="card">
      {error && <ErrorBanner error={error} />}

      {renaming ? (
        <form onSubmit={(event) => void saveRename(event)}>
          <RequiredLegend />
          <Field id={`preset-name-${preset.id}`} label="Nome" required>
            <input
              {...fieldAria(`preset-name-${preset.id}`)}
              required
              maxLength={120}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field id={`preset-desc-${preset.id}`} label="Descrizione" optional>
            <input
              {...fieldAria(`preset-desc-${preset.id}`)}
              maxLength={500}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
          <div className="form-actions">
            <button type="submit" className="primary" disabled={busy !== null}>
              {busy !== null ? "Salvataggio…" : "Salva"}
            </button>
            <button type="button" onClick={() => setRenaming(false)}>
              Annulla
            </button>
          </div>
        </form>
      ) : (
        <>
          <h3>
            {preset.name}{" "}
            <span className="status-pill">
              {preset.builtin_key ? "predefinito" : "personalizzato"}
            </span>
          </h3>
          {preset.description && <p>{preset.description}</p>}
          <p className="card-hint">
            {preset.rules_count} regole · applicato a {preset.receivers_count} receiver
          </p>
        </>
      )}

      <div className="toolbar">
        <button onClick={() => setOpen(!open)}>
          {open ? "Nascondi regole" : "Mostra regole"}
        </button>
        {canManage && !renaming && (
          <>
            <button onClick={() => setRenaming(true)}>Rinomina</button>
            {preset.builtin_key && (
              <button
                disabled={busy !== null}
                onClick={() =>
                  void mutate(
                    () => apiPost(`/api/v1/severity-presets/${preset.id}/reset`),
                    `Preset «${preset.name}» riportato ai valori predefiniti.`,
                  )
                }
              >
                Ripristina i valori predefiniti
              </button>
            )}
            <button className="danger" onClick={() => setConfirmDelete(true)}>
              Elimina preset
            </button>
          </>
        )}
      </div>

      {confirmDelete && (
        <ConfirmDialog
          title={`Elimina preset "${preset.name}"`}
          expectedText={preset.name}
          confirmLabel="Elimina preset"
          onConfirm={() => {
            setConfirmDelete(false);
            void mutate(
              () => apiDelete(`/api/v1/severity-presets/${preset.id}`),
              `Preset «${preset.name}» eliminato.`,
            );
          }}
          onCancel={() => setConfirmDelete(false)}
        >
          <p>
            Il preset viene tolto dai {preset.receivers_count} receiver che lo usano: quei receiver
            continueranno a valutare solo le proprie regole.
          </p>
        </ConfirmDialog>
      )}

      {open && <PresetRules presetId={preset.id} canManage={canManage} />}
    </div>
  );
}

function NewPresetForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (name.trim() === "") {
      setNameError("Il nome del preset è obbligatorio.");
      return;
    }
    setNameError(null);
    const ok = await run(
      async () => {
        await apiPost("/api/v1/severity-presets", { name: name.trim(), description });
        await queryClient.invalidateQueries({ queryKey: ["presets"] });
      },
      { success: `Preset «${name.trim()}» creato.` },
    );
    if (ok) {
      setName("");
      setDescription("");
    }
  }

  return (
    <details className="card collapsible">
      <summary>Nuovo preset</summary>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
        <RequiredLegend />
        <Field id="new-preset-name" label="Nome" required error={nameError}>
          <input
            {...fieldAria("new-preset-name", { error: nameError })}
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field
          id="new-preset-description"
          label="Descrizione"
          optional
          hint="A cosa serve questo preset: si legge nell'elenco e nella pagina del receiver."
        >
          <input
            {...fieldAria("new-preset-description", { hint: true })}
            maxLength={500}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Creazione…" : "Crea preset"}
          </button>
        </div>
      </form>
    </details>
  );
}

function MissingBuiltins({ missing }: { missing: BuiltinPresetOut[] }) {
  const queryClient = useQueryClient();
  const [installed, setInstalled] = useState<string[] | null>(null);
  const { busy, error, run } = useAction();

  async function install() {
    await run(
      async () => {
        const result = await apiPost<SyncBuiltinPresetsOut>(
          "/api/v1/severity-presets/sync-builtin",
        );
        setInstalled(result.installed);
        await queryClient.invalidateQueries({ queryKey: ["presets"] });
        await queryClient.invalidateQueries({ queryKey: ["presets-catalog"] });
      },
      { success: "Preset predefiniti installati nel tenant." },
    );
  }

  if (installed !== null) {
    return (
      <div className="card">
        <p>Preset installati: {installed.length > 0 ? installed.join(", ") : "nessuno"}.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Preset predefiniti non ancora installati</h3>
      </div>
      {error && <ErrorBanner error={error} />}
      <p className="card-hint">
        Vengono copiati dentro il tuo tenant: da quel momento si modificano come tutti gli altri e
        gli aggiornamenti dell'applicazione non li sovrascrivono.
      </p>
      <ul>
        {missing.map((builtin) => (
          <li key={builtin.key}>
            <strong>{builtin.name}</strong> — {builtin.description} ({builtin.rules_count} regole)
          </li>
        ))}
      </ul>
      <button className="primary" disabled={busy !== null} onClick={() => void install()}>
        {busy !== null ? "Installazione…" : `Installa i ${missing.length} preset mancanti`}
      </button>
    </div>
  );
}

export default function PresetsPage() {
  const { role } = useSession();
  const canManage = hasRole(role, ADMIN_ROLES);

  const { data: presets, isLoading, error } = useQuery<SeverityPresetOut[], ApiError>({
    queryKey: ["presets"],
    queryFn: () => apiGet<SeverityPresetOut[]>("/api/v1/severity-presets"),
  });

  const { data: catalog } = useQuery<BuiltinPresetOut[], ApiError>({
    queryKey: ["presets-catalog"],
    queryFn: () => apiGet<BuiltinPresetOut[]>("/api/v1/severity-presets/catalog"),
  });

  const missing = (catalog ?? []).filter((builtin) => !builtin.installed);

  return (
    <div>
      <div className="page-header">
        <h1>Preset di regole</h1>
      </div>
      <div className="card">
        <p>
          Un preset è un insieme di regole di severity riusabile: si scrive una volta e si applica a
          quanti receiver si vuole, dalla pagina del receiver. Modificare un preset cambia il
          comportamento di <strong>tutti</strong> i receiver che lo usano.
        </p>
        <p className="card-hint">
          Sul singolo receiver, le regole scritte lì valgono prima di quelle dei preset: servono a
          fare l'eccezione senza duplicare il preset.
        </p>
      </div>

      {error && <ErrorBanner error={error} />}
      {canManage && missing.length > 0 && <MissingBuiltins missing={missing} />}
      {canManage && <NewPresetForm />}

      {isLoading && <EmptyState message="Caricamento…" />}
      {presets?.length === 0 && !isLoading && (
        <p className="card-hint">Nessun preset in questo tenant.</p>
      )}
      {presets?.map((preset) => (
        <PresetCard key={preset.id} preset={preset} canManage={canManage} />
      ))}
    </div>
  );
}
