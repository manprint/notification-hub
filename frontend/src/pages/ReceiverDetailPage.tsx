import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiDelete, apiGet, apiGetFile, apiPatch, apiPost } from "../api/client";
import type { ApiError, ReceiverOut, Severity } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import CopyButton from "../components/CopyButton";
import Detail from "../components/Detail";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import ReceiverPresetsPanel from "../components/ReceiverPresetsPanel";
import SeverityRulesPanel from "../components/SeverityRulesPanel";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import {
  formatExecutionPreview,
  nextCronExecutions,
  validateCronExpression,
  validateTimezone,
} from "../lib/cron";
import {
  DURATION_UNIT_LABELS,
  type DurationUnit,
  formatDurationSeconds,
  formatIntervalSeconds,
  splitDuration,
  toSeconds,
} from "../lib/duration";
import { formatBytes, formatInstantOr } from "../lib/format";
import { ADMIN_ROLES, MEMBER_ROLES, hasRole } from "../lib/roles";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];
const EXIT_CODE_DISABLED = "";
const DURATION_DISABLED = "";
const DURATION_UNITS: DurationUnit[] = ["s", "m", "h", "g"];

/** Modi di dichiarare l'attesa di un receiver: nessuna sorveglianza, intervallo
 *  fisso, oppure la stessa espressione che sta nel crontab. Sono alternativi,
 *  perche' l'intervallo e il cron dicono la stessa cosa in due modi. */
type ExpectedMode = "off" | "interval" | "cron";

const EXPECTED_MODE_LABELS: Record<ExpectedMode, string> = {
  off: "nessuna sorveglianza",
  interval: "intervallo fisso",
  cron: "espressione cron",
};

const DEFAULT_GRACE_SECONDS = 300;
// Stesso default del backend (app/services/surveillance.py): un'espressione cron
// senza fuso dichiarato viene valutata in UTC.
const DEFAULT_TIMEZONE = "UTC";

function initialExpectedMode(receiver: ReceiverOut): ExpectedMode {
  if (receiver.expected_cron !== null) return "cron";
  if (receiver.expected_every_seconds !== null) return "interval";
  return "off";
}

/** Tutti i fusi noti a questo browser. `Intl.supportedValuesOf` non esiste in
 *  ogni runtime, quindi l'assenza va gestita: senza elenco restano comunque
 *  selezionabili i "Consigliati" (UTC, fuso del browser, valore salvato). */
function knownTimezones(): string[] {
  const intl = Intl as typeof Intl & {
    supportedValuesOf?: (key: string) => string[];
  };
  try {
    return intl.supportedValuesOf?.("timeZone") ?? [];
  } catch {
    return [];
  }
}

/** Fuso di questa macchina: nella pratica e' la scelta giusta quasi sempre,
 *  perche' il crontab da sorvegliare sta su un server configurato come chi lo
 *  legge. */
function browserTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/** I fusi da mettere nel menu, raggruppati per area.
 *
 *  Un `<select>` e non un campo con `datalist`: con la datalist il browser
 *  filtra i suggerimenti per sottostringa del valore gia' scritto, quindi con
 *  "UTC" nel campo si vedeva solo "UTC" e la lista sembrava vuota.
 *
 *  Il valore corrente viene sempre incluso, anche se questo browser non lo
 *  conosce: un fuso salvato non deve sparire dal menu e diventare un altro al
 *  primo salvataggio. */
function timezoneGroups(current: string): { label: string; zones: string[] }[] {
  const consigliati = [
    ...new Set([DEFAULT_TIMEZONE, browserTimezone(), current].filter(Boolean) as string[]),
  ];

  const conosciuti = knownTimezones();
  const perArea = new Map<string, string[]>();
  for (const zone of conosciuti) {
    const separatore = zone.indexOf("/");
    const area = separatore === -1 ? "Altri" : zone.slice(0, separatore);
    const elenco = perArea.get(area);
    if (elenco) elenco.push(zone);
    else perArea.set(area, [zone]);
  }

  if (!conosciuti.includes(current)) {
    perArea.set("Altri", [...(perArea.get("Altri") ?? []), current]);
  }

  return [
    { label: "Consigliati", zones: consigliati },
    ...[...perArea.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([label, zones]) => ({ label, zones: [...zones].sort() })),
  ];
}

/** Riassunto leggibile dell'attesa configurata, per la vista di sola lettura. */
function describeExpectation(receiver: ReceiverOut): string {
  if (receiver.missing_severity === null) return "nessun effetto";
  const grace = formatIntervalSeconds(receiver.expected_grace_seconds ?? 0);
  const quando =
    receiver.expected_cron !== null
      ? `cron ${receiver.expected_cron} (${receiver.expected_timezone ?? DEFAULT_TIMEZONE})`
      : `ogni ${formatIntervalSeconds(receiver.expected_every_seconds ?? 0)}`;
  return `${quando}, tolleranza ${grace} → ${receiver.missing_severity}`;
}

function EditReceiverForm({ receiver, onDone }: { receiver: ReceiverOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const { busy, error, run } = useAction();
  const [name, setName] = useState(receiver.name);
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>(receiver.default_severity);
  const [maxBodyBytes, setMaxBodyBytes] = useState(receiver.max_body_bytes);
  const [rateLimitPerMin, setRateLimitPerMin] = useState(receiver.rate_limit_per_min);
  const [exitCodeSeverity, setExitCodeSeverity] = useState<string>(
    receiver.exit_code_severity ?? EXIT_CODE_DISABLED,
  );
  const initialThreshold = splitDuration(receiver.duration_threshold_seconds);
  const [durationAmount, setDurationAmount] = useState(initialThreshold.amount);
  const [durationUnit, setDurationUnit] = useState<DurationUnit>(initialThreshold.unit);
  const [durationSeverity, setDurationSeverity] = useState<string>(
    receiver.duration_severity ?? DURATION_DISABLED,
  );
  const [expectedMode, setExpectedMode] = useState<ExpectedMode>(initialExpectedMode(receiver));
  const initialInterval = splitDuration(receiver.expected_every_seconds);
  const [intervalAmount, setIntervalAmount] = useState(initialInterval.amount || "1");
  const [intervalUnit, setIntervalUnit] = useState<DurationUnit>(
    receiver.expected_every_seconds === null ? "g" : initialInterval.unit,
  );
  const [cron, setCron] = useState(receiver.expected_cron ?? "");
  const [timezone, setTimezone] = useState(
    receiver.expected_timezone ?? browserTimezone() ?? DEFAULT_TIMEZONE,
  );
  const initialGrace = splitDuration(receiver.expected_grace_seconds ?? DEFAULT_GRACE_SECONDS);
  const [graceAmount, setGraceAmount] = useState(initialGrace.amount);
  const [graceUnit, setGraceUnit] = useState<DurationUnit>(initialGrace.unit);
  const [missingSeverity, setMissingSeverity] = useState<Severity>(
    receiver.missing_severity ?? "critical",
  );
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Validazione dell'espressione cron mentre si scrive: bloccante al salvataggio
  // e mostrata sotto il campo. Vale solo nel modo cron.
  const cronError = expectedMode === "cron" ? validateCronExpression(cron) : null;
  // Prossime tre occorrenze, solo per un cron valido nel fuso scelto.
  const nextExecutions =
    expectedMode === "cron" && cronError === null
      ? nextCronExecutions(cron.trim(), timezone.trim() || "UTC")
      : [];

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setNameError(null);

    if (name.trim() === "") {
      setNameError("Il nome del receiver è obbligatorio.");
      return;
    }

    // Soglia e severity vanno insieme: il backend rifiuta con 422 la coppia
    // mezza configurata, ma dirlo qui costa un giro di rete in meno e spiega
    // meglio quale dei due campi manca.
    const amount = Number(durationAmount);
    const hasAmount = durationAmount.trim() !== "" && Number.isFinite(amount) && amount > 0;
    const hasSeverity = durationSeverity !== DURATION_DISABLED;
    if (hasAmount !== hasSeverity) {
      setFormError(
        hasAmount
          ? "Scegli la severity da applicare oltre la soglia di durata, o svuota la soglia."
          : "Imposta una soglia di durata maggiore di zero, o riporta la severity a «nessun effetto».",
      );
      return;
    }

    // Sorveglianza dell'attesa: i campi che contano dipendono dal modo scelto,
    // e un cron vuoto o un intervallo a zero non e' una politica.
    const graceValue = Number(graceAmount);
    const graceOk =
      graceAmount.trim() !== "" && Number.isFinite(graceValue) && graceValue >= 0;
    const intervalValue = Number(intervalAmount);
    if (expectedMode !== "off" && !graceOk) {
      setFormError("Indica la tolleranza sul ritardo (anche zero, se il job e' puntuale).");
      return;
    }
    if (expectedMode === "interval" && !(Number.isFinite(intervalValue) && intervalValue > 0)) {
      setFormError("Indica ogni quanto ti aspetti un invio, come numero maggiore di zero.");
      return;
    }
    if (expectedMode === "cron") {
      const err = validateCronExpression(cron);
      if (err !== null) {
        setFormError(err);
        return;
      }
      const tzErr = validateTimezone(timezone.trim() || "UTC");
      if (tzErr !== null) {
        setFormError(tzErr);
        return;
      }
    }

    const expected =
      expectedMode === "off"
        ? {
            expected_every_seconds: null,
            expected_cron: null,
            expected_timezone: null,
            expected_grace_seconds: null,
            missing_severity: null,
          }
        : {
            expected_every_seconds:
              expectedMode === "interval" ? toSeconds(intervalValue, intervalUnit) : null,
            expected_cron: expectedMode === "cron" ? cron.trim() : null,
            expected_timezone: expectedMode === "cron" ? timezone.trim() || "UTC" : null,
            expected_grace_seconds: toSeconds(graceValue, graceUnit),
            missing_severity: missingSeverity,
          };

    const ok = await run(
      async () => {
        await apiPatch(`/api/v1/receivers/${receiver.id}`, {
          name: name.trim(),
          default_severity: defaultSeverity,
          max_body_bytes: maxBodyBytes,
          rate_limit_per_min: rateLimitPerMin,
          // null e' un valore, non "campo assente": disattiva la politica.
          exit_code_severity:
            exitCodeSeverity === EXIT_CODE_DISABLED ? null : exitCodeSeverity,
          duration_threshold_seconds: hasAmount ? toSeconds(amount, durationUnit) : null,
          duration_severity: hasSeverity ? durationSeverity : null,
          ...expected,
        });
        await queryClient.invalidateQueries({ queryKey: ["receiver", receiver.id] });
      },
      { success: "Impostazioni del receiver salvate." },
    );
    if (ok) onDone();
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <RequiredLegend />

      <div className="form-grid">
        <Field id="receiver-edit-name" label="Nome" required error={nameError}>
          <input
            {...fieldAria("receiver-edit-name", { error: nameError })}
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="receiver-edit-severity" label="Severity di default" required>
          <select
            {...fieldAria("receiver-edit-severity")}
            value={defaultSeverity}
            onChange={(event) => setDefaultSeverity(event.target.value as Severity)}
          >
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field id="receiver-edit-body" label="Limite corpo (byte)" required>
          <input
            {...fieldAria("receiver-edit-body")}
            type="number"
            min={1}
            required
            value={maxBodyBytes}
            onChange={(event) => setMaxBodyBytes(Number(event.target.value))}
          />
        </Field>
        <Field id="receiver-edit-rate" label="Rate limit (al minuto)" required>
          <input
            {...fieldAria("receiver-edit-rate")}
            type="number"
            min={0}
            required
            value={rateLimitPerMin}
            onChange={(event) => setRateLimitPerMin(Number(event.target.value))}
          />
        </Field>
      </div>

      <fieldset>
        <legend>Severity decisa dall'esecuzione</legend>
        <p className="card-hint">
          Quello che il job dichiara di sé negli header (<code>X-Exit-Code</code>,{" "}
          <code>X-Duration-Ms</code>) può alzare la severity senza scrivere regole sul testo.
        </p>
        <div className="form-grid">
          <Field id="receiver-edit-exit-code" label="Severity per exit code diverso da zero">
            <select
              {...fieldAria("receiver-edit-exit-code")}
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
          </Field>
          <Field id="receiver-edit-duration-threshold" label="Soglia di durata">
            <div className="input-with-unit">
              <input
                {...fieldAria("receiver-edit-duration-threshold")}
                type="number"
                min={1}
                placeholder="nessuna"
                value={durationAmount}
                onChange={(event) => setDurationAmount(event.target.value)}
              />
              <select
                aria-label="Unita della soglia di durata"
                value={durationUnit}
                onChange={(event) => setDurationUnit(event.target.value as DurationUnit)}
              >
                {DURATION_UNITS.map((unit) => (
                  <option key={unit} value={unit}>
                    {DURATION_UNIT_LABELS[unit]}
                  </option>
                ))}
              </select>
            </div>
          </Field>
          <Field id="receiver-edit-duration-severity" label="Severity oltre la soglia di durata">
            <select
              {...fieldAria("receiver-edit-duration-severity")}
              value={durationSeverity}
              onChange={(event) => setDurationSeverity(event.target.value)}
            >
              <option value={DURATION_DISABLED}>nessun effetto</option>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </fieldset>

      <fieldset>
        <legend>Sorveglianza dell'attesa</legend>
        <p className="card-hint">
          Notifica quando un invio <strong>non</strong> arriva: macchina spenta, cron rimosso, rete
          verso NotifyHub assente. Se il job usa <code>--only-on-failure</code> non va sorvegliato
          cosi': un'esecuzione riuscita non manda niente e verrebbe segnalata come assenza. Con{" "}
          <code>--ping-start</code> l'allarme dice anche se il job non e' partito o se e' partito e
          non ha concluso.
        </p>
        <Field
          id="receiver-edit-expected-mode"
          label="Attesa"
          required
          hint="Intervallo e cron dicono la stessa cosa in due modi: se ne sceglie uno."
        >
          <select
            {...fieldAria("receiver-edit-expected-mode", { hint: true })}
            value={expectedMode}
            onChange={(event) => setExpectedMode(event.target.value as ExpectedMode)}
          >
            {(Object.keys(EXPECTED_MODE_LABELS) as ExpectedMode[]).map((mode) => (
              <option key={mode} value={mode}>
                {EXPECTED_MODE_LABELS[mode]}
              </option>
            ))}
          </select>
        </Field>

        {expectedMode === "interval" && (
          <Field id="receiver-edit-expected-interval" label="Mi aspetto un invio ogni" required>
            <div className="input-with-unit">
              <input
                {...fieldAria("receiver-edit-expected-interval")}
                type="number"
                min={1}
                required
                value={intervalAmount}
                onChange={(event) => setIntervalAmount(event.target.value)}
              />
              <select
                aria-label="Unita dell'intervallo atteso"
                value={intervalUnit}
                onChange={(event) => setIntervalUnit(event.target.value as DurationUnit)}
              >
                {DURATION_UNITS.map((unit) => (
                  <option key={unit} value={unit}>
                    {DURATION_UNIT_LABELS[unit]}
                  </option>
                ))}
              </select>
            </div>
          </Field>
        )}

        {expectedMode === "cron" && (
          <>
            <div className="form-grid">
              <Field
                id="receiver-edit-expected-cron"
                label="Espressione cron"
                required
                error={cronError}
              >
                <input
                  {...fieldAria("receiver-edit-expected-cron", { error: cronError })}
                  placeholder="0 3 * * 1-5"
                  required
                  value={cron}
                  onChange={(event) => setCron(event.target.value)}
                />
              </Field>
              <Field id="receiver-edit-expected-timezone" label="Fuso dell'espressione" required>
                <select
                  {...fieldAria("receiver-edit-expected-timezone")}
                  value={timezone}
                  onChange={(event) => setTimezone(event.target.value)}
                >
                  {timezoneGroups(timezone).map((gruppo) => (
                    <optgroup key={gruppo.label} label={gruppo.label}>
                      {gruppo.zones.map((zone) => (
                        <option key={`${gruppo.label}:${zone}`} value={zone}>
                          {zone}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </Field>
            </div>
            {nextExecutions.length > 0 ? (
              <ul className="cron-preview" aria-label="Prossime esecuzioni">
                {nextExecutions.map((data) => (
                  <li key={data.toISOString()}>
                    {formatExecutionPreview(data, timezone.trim() || "UTC")}
                  </li>
                ))}
              </ul>
            ) : (
              cronError === null && (
                <p className="card-hint">
                  Nessuna esecuzione trovata per questa espressione cron.
                </p>
              )
            )}
            <p className="card-hint">
              La stessa riga che sta nel crontab della macchina, con il fuso in cui quella macchina
              la interpreta. In cima trovi UTC e il fuso di questo browser, poi tutti gli altri
              raggruppati per area.
            </p>
          </>
        )}

        {expectedMode !== "off" && (
          <div className="form-grid">
            <Field
              id="receiver-edit-expected-grace"
              label="Tolleranza sul ritardo"
              required
              hint="Quanto si aspetta dopo l'orario previsto prima di gridare."
            >
              <div className="input-with-unit">
                <input
                  {...fieldAria("receiver-edit-expected-grace", { hint: true })}
                  type="number"
                  min={0}
                  required
                  value={graceAmount}
                  onChange={(event) => setGraceAmount(event.target.value)}
                />
                <select
                  aria-label="Unita della tolleranza"
                  value={graceUnit}
                  onChange={(event) => setGraceUnit(event.target.value as DurationUnit)}
                >
                  {DURATION_UNITS.map((unit) => (
                    <option key={unit} value={unit}>
                      {DURATION_UNIT_LABELS[unit]}
                    </option>
                  ))}
                </select>
              </div>
            </Field>
            <Field id="receiver-edit-missing-severity" label="Severity dell'assenza" required>
              <select
                {...fieldAria("receiver-edit-missing-severity")}
                value={missingSeverity}
                onChange={(event) => setMissingSeverity(event.target.value as Severity)}
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
      </fieldset>

      {formError && (
        <p className="error-banner" role="alert">
          {formError}
        </p>
      )}
      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy !== null}>
          {busy !== null ? "Salvataggio…" : "Salva"}
        </button>
        <button type="button" onClick={onDone}>
          Annulla
        </button>
      </div>
    </form>
  );
}

function DownloadWrapperButton({ receiver }: { receiver: ReceiverOut }) {
  const { busy, error, run } = useAction();

  async function download() {
    await run(async () => {
      // Il file arriva dal backend gia' compilato: URL pubblica dell'istanza e
      // slug di questo receiver. Ricostruirlo qui vorrebbe dire indovinare
      // l'URL dal browser e rischiare che i due non coincidano.
      const { content, filename } = await apiGetFile(
        `/api/v1/receivers/${receiver.id}/wrapper-script`,
        "notifyhub-run.sh",
      );
      const url = URL.createObjectURL(new Blob([content], { type: "text/x-shellscript" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    });
  }

  return (
    <>
      {error && <ErrorBanner error={error} />}
      <button onClick={() => void download()} disabled={busy !== null}>
        {busy !== null ? "Preparazione…" : "Scarica lo script"}
      </button>
    </>
  );
}

export default function ReceiverDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { role } = useSession();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { busy, error: actionError, run } = useAction();
  const [editing, setEditing] = useState(false);
  // Una sola conferma aperta alla volta: le tre azioni che cambiano qualcosa in
  // modo non banale (slug, stato, esistenza) passano tutte di qui.
  const [confirming, setConfirming] = useState<"rotate" | "status" | "delete" | null>(null);

  const {
    data: receiver,
    isLoading,
    error,
  } = useQuery<ReceiverOut, ApiError>({
    queryKey: ["receiver", id],
    queryFn: () => apiGet<ReceiverOut>(`/api/v1/receivers/${id}`),
    enabled: Boolean(id),
  });

  async function rotateSlug() {
    setConfirming(null);
    await run(
      async () => {
        await apiPost(`/api/v1/receivers/${id}/rotate-slug`);
        await queryClient.invalidateQueries({ queryKey: ["receiver", id] });
      },
      { name: "rotate", success: "Slug rigenerato: aggiorna i job che inviano qui." },
    );
  }

  async function toggleStatus(disable: boolean) {
    setConfirming(null);
    await run(
      async () => {
        await apiPatch(`/api/v1/receivers/${id}`, { status: disable ? "disabled" : "active" });
        await queryClient.invalidateQueries({ queryKey: ["receiver", id] });
      },
      {
        name: "status",
        success: disable
          ? "Receiver disabilitato: gli invii verranno rifiutati."
          : "Receiver riattivato: la sorveglianza riparte da adesso.",
      },
    );
  }

  async function removeReceiver() {
    setConfirming(null);
    const ok = await run(async () => apiDelete(`/api/v1/receivers/${id}`), {
      name: "delete",
      success: "Receiver eliminato.",
    });
    if (ok) navigate("/groups", { replace: true });
  }

  if (isLoading) return <EmptyState message="Caricamento…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!receiver) return null;

  const canManage = hasRole(role, MEMBER_ROLES);
  const disabled = receiver.status === "disabled";
  // URL dal backend, non da window.location: e' la stessa che finisce nello
  // script scaricabile, quindi i due non possono divergere dietro reverse proxy.
  const curlCommand = `curl --data "corpo del messaggio" ${receiver.ingest_url}`;

  return (
    <div>
      <Link className="back-link" to={`/groups/${receiver.group_id}`}>
        ← Torna al gruppo
      </Link>
      <div className="page-header">
        <h1>
          {receiver.name}
          {disabled && <span className="status-pill warn">disabilitato</span>}
        </h1>
        {!editing && (
          <div className="page-header-actions">
            {canManage && (
              <button className="primary" onClick={() => setEditing(true)}>
                Modifica receiver
              </button>
            )}
            <DownloadWrapperButton receiver={receiver} />
            {hasRole(role, ADMIN_ROLES) && (
              <button disabled={busy !== null} onClick={() => setConfirming("rotate")}>
                Rigenera slug
              </button>
            )}
            {canManage && (
              <button disabled={busy !== null} onClick={() => setConfirming("status")}>
                {disabled ? "Riattiva receiver" : "Disabilita receiver"}
              </button>
            )}
            {canManage && (
              <button
                className="danger"
                disabled={busy !== null}
                onClick={() => setConfirming("delete")}
              >
                Elimina receiver
              </button>
            )}
          </div>
        )}
      </div>
      {actionError && <ErrorBanner error={actionError} />}

      {editing ? (
        <div className="card">
          <div className="card-header">
            <h2>Modifica receiver</h2>
          </div>
          <EditReceiverForm receiver={receiver} onDone={() => setEditing(false)} />
        </div>
      ) : (
        <>
          <div className="card">
            <div className="card-header">
              <h2>Come inviare qui</h2>
            </div>
            <div className="detail-grid">
              <Detail label="Slug">
                <span className="copy-field">
                  <code>{receiver.slug}</code>
                  <CopyButton value={receiver.slug} label="Copia slug" />
                </span>
              </Detail>
              <Detail label="URL di invio">
                <span className="copy-field">
                  <code>{receiver.ingest_url}</code>
                  <CopyButton value={receiver.ingest_url} label="Copia URL" />
                </span>
              </Detail>
              <Detail label="Comando di prova" wide>
                <span className="copy-field">
                  <code>{curlCommand}</code>
                  <CopyButton value={curlCommand} label="Copia comando" />
                </span>
              </Detail>
            </div>
            <p className="card-hint">
              Per i job da crontab: <code>notifyhub-run.sh</code> con URL e slug gia' compilati,
              scritti in due variabili in cima al file e modificabili a mano.
            </p>
            {disabled && (
              <div className="error-banner">
                Receiver disabilitato: {receiver.rejected_last_24h ?? 0} richieste rifiutate nelle
                ultime 24 ore.
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Configurazione</h2>
            </div>
            <div className="detail-grid">
              <Detail label="Stato del receiver">
                <span className={`status-pill ${disabled ? "warn" : "ok"}`}>
                  {disabled ? "disabilitato" : "attivo"}
                </span>
              </Detail>
              <Detail label="Severity di default">{receiver.default_severity}</Detail>
              <Detail label="Severity per exit code diverso da zero">
                {receiver.exit_code_severity ?? "nessun effetto"}
              </Detail>
              <Detail label="Soglia di durata">
                {receiver.duration_threshold_seconds !== null &&
                receiver.duration_severity !== null
                  ? `oltre ${formatDurationSeconds(receiver.duration_threshold_seconds)} → ${receiver.duration_severity}`
                  : "nessun effetto"}
              </Detail>
              <Detail label="Limite corpo">
                {formatBytes(receiver.max_body_bytes)}
                <div className="cell-diagnostics">{receiver.max_body_bytes} byte</div>
              </Detail>
              <Detail label="Rate limit">{receiver.rate_limit_per_min}/min</Detail>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2>Sorveglianza dell'attesa</h2>
            </div>
            {receiver.expected_late && (
              <div className="error-banner" role="alert">
                In ritardo: nessun invio entro la scadenza.
                {receiver.missing_alerted_at !== null
                  ? ` Assenza segnalata il ${formatInstantOr(receiver.missing_alerted_at, "mai")}.`
                  : " La notifica di assenza parte al prossimo controllo (entro un minuto)."}
              </div>
            )}
            <div className="detail-grid">
              <Detail label="Politica in vigore" wide>
                {describeExpectation(receiver)}
              </Detail>
              {receiver.missing_severity !== null && (
                <>
                  <Detail label="Ultima conclusione">
                    {formatInstantOr(receiver.last_notification_at, "mai")}
                  </Detail>
                  <Detail label="Ultimo avvio">
                    {formatInstantOr(receiver.last_start_at, "mai")}
                  </Detail>
                  <Detail label="Allarme se non arriva entro">
                    {formatInstantOr(receiver.expected_deadline_at, "—")}
                  </Detail>
                </>
              )}
            </div>
            {receiver.missing_severity === null && (
              <p className="card-hint">
                Nessuna sorveglianza: se questo receiver smette di inviare, non lo dice nessuno. Si
                accende da «Modifica receiver».
              </p>
            )}
          </div>
        </>
      )}

      <ReceiverPresetsPanel receiverId={receiver.id} />
      <SeverityRulesPanel receiver={receiver} />

      {confirming === "rotate" && (
        <ConfirmDialog
          title="Rigenera lo slug di invio"
          confirmLabel="Rigenera slug"
          onConfirm={() => void rotateSlug()}
          onCancel={() => setConfirming(null)}
        >
          <p>
            Il vecchio slug smette di funzionare <strong>subito</strong>: ogni job che invia al
            vecchio indirizzo riceverà 404 finché non lo aggiorni.
          </p>
          <p>Si rigenera quando lo slug è finito dove non doveva (un log, una repo pubblica).</p>
        </ConfirmDialog>
      )}

      {confirming === "status" && (
        <ConfirmDialog
          title={disabled ? "Riattiva questo receiver" : "Disabilita questo receiver"}
          confirmLabel={disabled ? "Riattiva receiver" : "Disabilita receiver"}
          destructive={!disabled}
          onConfirm={() => void toggleStatus(!disabled)}
          onCancel={() => setConfirming(null)}
        >
          {disabled ? (
            <p>
              Gli invii tornano ad essere accettati. Se la sorveglianza dell'attesa è accesa, la
              finestra riparte da adesso: nessun allarme per il tempo in cui era spento.
            </p>
          ) : (
            <p>
              Gli invii verranno rifiutati con 404, come per uno slug inesistente, e la
              sorveglianza dell'attesa non segnala più le assenze. Niente viene cancellato.
            </p>
          )}
        </ConfirmDialog>
      )}

      {confirming === "delete" && (
        <ConfirmDialog
          title={`Elimina receiver "${receiver.name}"`}
          confirmLabel="Elimina receiver"
          expectedText={receiver.name}
          onConfirm={() => void removeReceiver()}
          onCancel={() => setConfirming(null)}
        >
          <p>Verranno eliminate anche le notifiche e le consegne collegate a questo receiver.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}
