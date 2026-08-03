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
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";
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
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const body = { pattern, severity, case_insensitive: caseInsensitive };
      if (rule) {
        await apiPatch(`/api/v1/severity-preset-rules/${rule.id}`, body);
      } else {
        // Nessuna priorità: il backend accoda. L'ordine si cambia con le frecce.
        await apiPost(`/api/v1/severity-presets/${presetId}/rules`, { ...body, enabled: true });
        setPattern("");
      }
      await queryClient.invalidateQueries({ queryKey: ["preset", presetId] });
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <div className="toolbar">
        <input
          aria-label="Pattern RE2 del preset"
          placeholder="Pattern RE2, es. No space left on device"
          value={pattern}
          onChange={(event) => setPattern(event.target.value)}
          required
          maxLength={200}
          style={{ minWidth: "18rem" }}
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
        <button type="submit" className="primary">
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
  const [error, setError] = useState<ApiError | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  const { data, error: loadError } = useQuery<SeverityPresetDetailOut, ApiError>({
    queryKey: ["preset", presetId],
    queryFn: () => apiGet<SeverityPresetDetailOut>(`/api/v1/severity-presets/${presetId}`),
  });

  const rules = data?.rules ?? [];

  async function mutate(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey: ["preset", presetId] });
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  function move(index: number, delta: number) {
    const next = [...rules];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    void mutate(() =>
      apiPut(`/api/v1/severity-presets/${presetId}/rules/order`, {
        rule_ids: next.map((r) => r.id),
      }),
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
                              void mutate(() =>
                                apiPatch(`/api/v1/severity-preset-rules/${rule.id}`, {
                                  enabled: !rule.enabled,
                                }),
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
                          <button onClick={() => setEditingId(rule.id)}>Modifica</button>
                          <button
                            onClick={() =>
                              void mutate(() =>
                                apiDelete(`/api/v1/severity-preset-rules/${rule.id}`),
                              )
                            }
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
  const [error, setError] = useState<ApiError | null>(null);

  async function mutate(action: () => Promise<unknown>): Promise<boolean> {
    setError(null);
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
      await queryClient.invalidateQueries({ queryKey: ["preset", preset.id] });
      await queryClient.invalidateQueries({ queryKey: ["presets-catalog"] });
      return true;
    } catch (err) {
      setError(err as ApiError);
      return false;
    }
  }

  async function saveRename(event: React.FormEvent) {
    event.preventDefault();
    // Il modulo resta aperto se il salvataggio fallisce (nome duplicato → 409):
    // chiuderlo comunque farebbe sparire il testo insieme all'errore.
    const ok = await mutate(() =>
      apiPatch(`/api/v1/severity-presets/${preset.id}`, { name, description }),
    );
    if (ok) setRenaming(false);
  }

  return (
    <div className="card">
      {error && <ErrorBanner error={error} />}

      {renaming ? (
        <form onSubmit={(event) => void saveRename(event)}>
          <div className="form-row">
            <label htmlFor={`preset-name-${preset.id}`}>Nome</label>
            <input
              id={`preset-name-${preset.id}`}
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="form-row">
            <label htmlFor={`preset-desc-${preset.id}`}>Descrizione</label>
            <input
              id={`preset-desc-${preset.id}`}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <div className="toolbar">
            <button type="submit" className="primary">
              Salva
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
                onClick={() =>
                  void mutate(() => apiPost(`/api/v1/severity-presets/${preset.id}/reset`))
                }
              >
                Ripristina i valori predefiniti
              </button>
            )}
            <button onClick={() => setConfirmDelete(true)}>Elimina preset</button>
          </>
        )}
      </div>

      {confirmDelete && (
        <ConfirmDialog
          title={`Elimina preset "${preset.name}"`}
          expectedText={preset.name}
          onConfirm={() => {
            setConfirmDelete(false);
            void mutate(() => apiDelete(`/api/v1/severity-presets/${preset.id}`));
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
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPost("/api/v1/severity-presets", { name, description });
      setName("");
      setDescription("");
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <div className="card">
      <h3>Nuovo preset</h3>
      {error && <ErrorBanner error={error} />}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-row">
          <label htmlFor="new-preset-name">Nome</label>
          <input
            id="new-preset-name"
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="new-preset-description">Descrizione</label>
          <input
            id="new-preset-description"
            maxLength={500}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <button type="submit" className="primary">
          Crea preset
        </button>
      </form>
    </div>
  );
}

function MissingBuiltins({ missing }: { missing: BuiltinPresetOut[] }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<ApiError | null>(null);
  const [installed, setInstalled] = useState<string[] | null>(null);

  async function install() {
    setError(null);
    try {
      const result = await apiPost<SyncBuiltinPresetsOut>(
        "/api/v1/severity-presets/sync-builtin",
      );
      setInstalled(result.installed);
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
      await queryClient.invalidateQueries({ queryKey: ["presets-catalog"] });
    } catch (err) {
      setError(err as ApiError);
    }
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
      <h3>Preset predefiniti non ancora installati</h3>
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
      <button className="primary" onClick={() => void install()}>
        Installa i {missing.length} preset mancanti
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
      <h1>Preset di regole</h1>
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

      {isLoading && <p>Caricamento…</p>}
      {presets?.length === 0 && !isLoading && (
        <p className="card-hint">Nessun preset in questo tenant.</p>
      )}
      {presets?.map((preset) => (
        <PresetCard key={preset.id} preset={preset} canManage={canManage} />
      ))}
    </div>
  );
}
