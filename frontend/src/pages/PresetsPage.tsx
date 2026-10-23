import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
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
import { useToast } from "../hooks/useToast";
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
  const patternErrorId = useId();
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
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
    // noValidate: il campo vuoto lo rifiuta handleSubmit, con il messaggio sotto.
    <form noValidate onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <div className="toolbar">
        <label className="inline-check">
          <span>Pattern</span>
          <input
            aria-describedby={patternError ? patternErrorId : undefined}
            aria-invalid={patternError ? true : undefined}
            placeholder="RE2, es. No space left on device"
            value={pattern}
            onChange={(event) => setPattern(event.target.value)}
            required
            maxLength={200}
            className="grow-input"
          />
        </label>
        <label className="inline-check">
          <span>Severity</span>
          <select value={severity} onChange={(event) => setSeverity(event.target.value as Severity)}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
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
      {patternError && (
        <p className="field-error" id={patternErrorId} role="alert">
          {patternError}
        </p>
      )}
    </form>
  );
}

function PresetRules({ presetId, canManage }: { presetId: string; canManage: boolean }) {
  const queryClient = useQueryClient();
  const { busy, error, run } = useAction();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingRule, setDeletingRule] = useState<SeverityPresetRuleOut | null>(null);

  const {
    data,
    error: loadError,
    isLoading,
  } = useQuery<SeverityPresetDetailOut, ApiError>({
    queryKey: ["preset", presetId],
    queryFn: () => apiGet<SeverityPresetDetailOut>(`/api/v1/severity-presets/${presetId}`),
  });

  const rules = data?.rules ?? [];
  // Il "non ha ancora regole" vale solo con la lista letta e vuota.
  const loaded = data !== undefined;

  async function mutate(action: () => Promise<unknown>, success: string): Promise<boolean> {
    return run(async () => {
      try {
        await action();
      } finally {
        await queryClient.invalidateQueries({ queryKey: ["preset", presetId] });
        await queryClient.invalidateQueries({ queryKey: ["presets"] });
      }
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

      {!loaded && isLoading && <p className="card-hint">Caricamento delle regole…</p>}
      {loaded && rules.length === 0 && (
        <p className="card-hint">Questo preset non ha ancora regole.</p>
      )}
      {loaded && rules.length > 0 && (
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
                            {/* Ferme mentre un'altra modifica e' in volo: il
                                secondo click calcolerebbe il nuovo ordine da
                                quello vecchio e annullerebbe il primo. */}
                            <button
                              aria-label={`Sposta su ${rule.pattern}`}
                              disabled={index === 0 || busy !== null}
                              onClick={() => move(index, -1)}
                            >
                              ↑
                            </button>
                            <button
                              aria-label={`Sposta giù ${rule.pattern}`}
                              disabled={index === rules.length - 1 || busy !== null}
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
                            disabled={busy !== null}
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
          onConfirm={async () => {
            const rule = deletingRule;
            const ok = await mutate(
              () => apiDelete(`/api/v1/severity-preset-rules/${rule.id}`),
              "Regola eliminata dal preset.",
            );
            if (ok) setDeletingRule(null);
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
  // Bozza del modulo "Rinomina": si riempie dal preset ogni volta che il modulo
  // si apre. Inizializzata una volta sola al montaggio, dopo un "Ripristina i
  // valori predefiniti" o un Annulla ripartiva dal testo vecchio.
  const [name, setName] = useState(preset.name);
  const [description, setDescription] = useState(preset.description);
  const [nameError, setNameError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const { busy, error, run } = useAction();

  async function mutate(action: () => Promise<unknown>, success: string): Promise<boolean> {
    return run(async () => {
      try {
        await action();
      } finally {
        await queryClient.invalidateQueries({ queryKey: ["presets"] });
        await queryClient.invalidateQueries({ queryKey: ["preset", preset.id] });
        await queryClient.invalidateQueries({ queryKey: ["presets-catalog"] });
      }
    }, { success });
  }

  function openRename() {
    setName(preset.name);
    setDescription(preset.description);
    setNameError(null);
    setRenaming(true);
  }

  function cancelRename() {
    // La bozza si scarta: riaprendo si riparte dal preset com'e' adesso.
    setRenaming(false);
    setNameError(null);
  }

  async function saveRename(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    // Nome ripulito dagli spazi: "   " non e' un nome, e "Foo " passava il
    // controllo dei duplicati del backend accanto a un "Foo" esistente.
    const cleanName = name.trim();
    if (cleanName === "") {
      setNameError("Il nome del preset è obbligatorio.");
      return;
    }
    setNameError(null);
    // Il modulo resta aperto se il salvataggio fallisce (nome duplicato → 409):
    // chiuderlo comunque farebbe sparire il testo insieme all'errore.
    const ok = await mutate(
      () =>
        apiPatch(`/api/v1/severity-presets/${preset.id}`, {
          name: cleanName,
          description: description.trim(),
        }),
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
          <Field id={`preset-name-${preset.id}`} label="Nome" required error={nameError}>
            <input
              {...fieldAria(`preset-name-${preset.id}`, { error: nameError })}
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
            <button type="button" onClick={cancelRename}>
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
            {preset.rules_count} {preset.rules_count === 1 ? "regola" : "regole"} · applicato a{" "}
            {preset.receivers_count} receiver
          </p>
        </>
      )}

      <div className="toolbar">
        <button onClick={() => setOpen(!open)}>
          {open ? "Nascondi regole" : "Mostra regole"}
        </button>
        {canManage && !renaming && (
          <>
            <button disabled={busy !== null} onClick={openRename}>
              Rinomina
            </button>
            {preset.builtin_key && (
              <button disabled={busy !== null} onClick={() => setConfirmReset(true)}>
                Ripristina i valori predefiniti
              </button>
            )}
            <button
              className="danger"
              disabled={busy !== null}
              onClick={() => setConfirmDelete(true)}
            >
              Elimina preset
            </button>
          </>
        )}
      </div>

      {confirmReset && (
        <ConfirmDialog
          title={`Ripristina "${preset.name}"`}
          confirmLabel="Ripristina"
          // Il dialogo resta aperto e occupato finché la richiesta non risponde.
          onConfirm={async () => {
            const ok = await mutate(
              () => apiPost(`/api/v1/severity-presets/${preset.id}/reset`),
              `Preset «${preset.name}» riportato ai valori predefiniti.`,
            );
            if (ok) setConfirmReset(false);
          }}
          onCancel={() => setConfirmReset(false)}
        >
          <p>
            Vanno perse le <strong>{preset.rules_count}</strong> regole attuali di questo preset,
            comprese quelle che hai scritto tu: vengono sostituite dalle regole predefinite. Anche
            nome e descrizione tornano quelli del catalogo.
          </p>
          <p>
            I {preset.receivers_count} receiver che lo usano applicheranno subito le regole nuove.
          </p>
        </ConfirmDialog>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title={`Elimina preset "${preset.name}"`}
          expectedText={preset.name}
          confirmLabel="Elimina preset"
          // Come per le regole: il dialogo resta aperto e occupato finché la
          // richiesta non risponde, e il secondo click non manda una seconda DELETE.
          onConfirm={async () => {
            const ok = await mutate(
              () => apiDelete(`/api/v1/severity-presets/${preset.id}`),
              `Preset «${preset.name}» eliminato.`,
            );
            if (ok) setConfirmDelete(false);
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

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
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
  const toast = useToast();
  const { busy, error, run } = useAction();

  async function install() {
    let installed: string[] = [];
    const ok = await run(async () => {
      const result = await apiPost<SyncBuiltinPresetsOut>("/api/v1/severity-presets/sync-builtin");
      installed = result.installed;
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
      await queryClient.invalidateQueries({ queryKey: ["presets-catalog"] });
    });
    // L'esito va nel toast e non in questa scheda: appena il catalogo si
    // aggiorna non manca piu' niente, la pagina smonta la scheda e un messaggio
    // scritto qui non si vedeva mai.
    if (ok) {
      toast.success(
        installed.length > 0
          ? `Preset installati: ${installed.join(", ")}.`
          : "Nessun preset da installare: erano già tutti presenti.",
      );
    }
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
            <strong>{builtin.name}</strong> — {builtin.description} ({builtin.rules_count}{" "}
            {builtin.rules_count === 1 ? "regola" : "regole"})
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
      <p className="page-subtitle">
        Un preset è un insieme di regole di severity riusabile: si scrive una volta e si applica a
        quanti receiver si vuole, dalla pagina del receiver. Modificare un preset cambia il
        comportamento di <strong>tutti</strong> i receiver che lo usano.
      </p>
      <p className="card-hint">
        Sul singolo receiver, le regole scritte lì valgono prima di quelle dei preset: servono a
        fare l'eccezione senza duplicare il preset.
      </p>

      {error && <ErrorBanner error={error} />}
      {canManage && missing.length > 0 && <MissingBuiltins missing={missing} />}
      {canManage && <NewPresetForm />}

      {isLoading && <EmptyState message="Caricamento…" />}
      {presets?.length === 0 && !isLoading && <EmptyState message="Nessun preset in questo tenant." />}
      {presets?.map((preset) => (
        <PresetCard key={preset.id} preset={preset} canManage={canManage} />
      ))}
    </div>
  );
}
