import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  apiDelete,
  apiGet,
  apiGetFile,
  apiPatch,
  apiPost,
} from "../api/client";
import type { ApiError, ReceiverOut, Severity } from "../api/types";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorBanner from "../components/ErrorBanner";
import ReceiverPresetsPanel from "../components/ReceiverPresetsPanel";
import SeverityRulesPanel from "../components/SeverityRulesPanel";
import { useSession } from "../hooks/useSession";
import {
  DURATION_UNIT_LABELS,
  type DurationUnit,
  formatDurationSeconds,
  formatIntervalSeconds,
  splitDuration,
  toSeconds,
} from "../lib/duration";
import { ADMIN_ROLES, MEMBER_ROLES, hasRole } from "../lib/roles";

const SEVERITIES: Severity[] = [
  "critical",
  "error",
  "warning",
  "info",
  "debug",
];
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

function initialExpectedMode(receiver: ReceiverOut): ExpectedMode {
  if (receiver.expected_cron !== null) return "cron";
  if (receiver.expected_every_seconds !== null) return "interval";
  return "off";
}

/** Elenco dei fusi del browser per la datalist: `Intl.supportedValuesOf` non
 *  esiste in ogni runtime (jsdom compreso), quindi resta un suggerimento. */
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

/** Riassunto leggibile dell'attesa configurata, per la vista di sola lettura. */
function describeExpectation(receiver: ReceiverOut): string {
  if (receiver.missing_severity === null) return "nessun effetto";
  const grace = formatIntervalSeconds(receiver.expected_grace_seconds ?? 0);
  const quando =
    receiver.expected_cron !== null
      ? `cron ${receiver.expected_cron} (${receiver.expected_timezone ?? "UTC"})`
      : `ogni ${formatIntervalSeconds(receiver.expected_every_seconds ?? 0)}`;
  return `${quando}, tolleranza ${grace} → ${receiver.missing_severity}`;
}

function formatInstant(value: string | null): string {
  return value === null ? "mai" : new Date(value).toLocaleString("it-IT");
}

function EditReceiverForm({
  receiver,
  onDone,
}: {
  receiver: ReceiverOut;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(receiver.name);
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>(
    receiver.default_severity,
  );
  const [maxBodyBytes, setMaxBodyBytes] = useState(receiver.max_body_bytes);
  const [rateLimitPerMin, setRateLimitPerMin] = useState(
    receiver.rate_limit_per_min,
  );
  const [exitCodeSeverity, setExitCodeSeverity] = useState<string>(
    receiver.exit_code_severity ?? EXIT_CODE_DISABLED,
  );
  const initialThreshold = splitDuration(receiver.duration_threshold_seconds);
  const [durationAmount, setDurationAmount] = useState(initialThreshold.amount);
  const [durationUnit, setDurationUnit] = useState<DurationUnit>(
    initialThreshold.unit,
  );
  const [durationSeverity, setDurationSeverity] = useState<string>(
    receiver.duration_severity ?? DURATION_DISABLED,
  );
  const [expectedMode, setExpectedMode] = useState<ExpectedMode>(
    initialExpectedMode(receiver),
  );
  const initialInterval = splitDuration(receiver.expected_every_seconds);
  const [intervalAmount, setIntervalAmount] = useState(
    initialInterval.amount || "1",
  );
  const [intervalUnit, setIntervalUnit] = useState<DurationUnit>(
    receiver.expected_every_seconds === null ? "g" : initialInterval.unit,
  );
  const [cron, setCron] = useState(receiver.expected_cron ?? "");
  const [timezone, setTimezone] = useState(receiver.expected_timezone ?? "UTC");
  const initialGrace = splitDuration(
    receiver.expected_grace_seconds ?? DEFAULT_GRACE_SECONDS,
  );
  const [graceAmount, setGraceAmount] = useState(initialGrace.amount);
  const [graceUnit, setGraceUnit] = useState<DurationUnit>(initialGrace.unit);
  const [missingSeverity, setMissingSeverity] = useState<Severity>(
    receiver.missing_severity ?? "critical",
  );
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setFormError(null);

    // Soglia e severity vanno insieme: il backend rifiuta con 422 la coppia
    // mezza configurata, ma dirlo qui costa un giro di rete in meno e spiega
    // meglio quale dei due campi manca.
    const amount = Number(durationAmount);
    const hasAmount =
      durationAmount.trim() !== "" && Number.isFinite(amount) && amount > 0;
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
      graceAmount.trim() !== "" &&
      Number.isFinite(graceValue) &&
      graceValue >= 0;
    const intervalValue = Number(intervalAmount);
    if (expectedMode !== "off" && !graceOk) {
      setFormError(
        "Indica la tolleranza sul ritardo (anche zero, se il job e' puntuale).",
      );
      return;
    }
    if (
      expectedMode === "interval" &&
      !(Number.isFinite(intervalValue) && intervalValue > 0)
    ) {
      setFormError(
        "Indica ogni quanto ti aspetti un invio, come numero maggiore di zero.",
      );
      return;
    }
    if (expectedMode === "cron" && cron.trim().split(/\s+/).length !== 5) {
      setFormError(
        "L'espressione cron deve avere 5 campi come in crontab: minuto ora giorno mese giorno-settimana.",
      );
      return;
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
              expectedMode === "interval"
                ? toSeconds(intervalValue, intervalUnit)
                : null,
            expected_cron: expectedMode === "cron" ? cron.trim() : null,
            expected_timezone:
              expectedMode === "cron" ? timezone.trim() || "UTC" : null,
            expected_grace_seconds: toSeconds(graceValue, graceUnit),
            missing_severity: missingSeverity,
          };

    try {
      await apiPatch(`/api/v1/receivers/${receiver.id}`, {
        name,
        default_severity: defaultSeverity,
        max_body_bytes: maxBodyBytes,
        rate_limit_per_min: rateLimitPerMin,
        // null e' un valore, non "campo assente": disattiva la politica.
        exit_code_severity:
          exitCodeSeverity === EXIT_CODE_DISABLED ? null : exitCodeSeverity,
        duration_threshold_seconds: hasAmount
          ? toSeconds(amount, durationUnit)
          : null,
        duration_severity: hasSeverity ? durationSeverity : null,
        ...expected,
      });
      await queryClient.invalidateQueries({
        queryKey: ["receiver", receiver.id],
      });
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
          onChange={(event) =>
            setDefaultSeverity(event.target.value as Severity)
          }
        >
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="receiver-edit-exit-code">
          Severity per exit code diverso da zero
        </label>
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
        <label htmlFor="receiver-edit-duration-threshold">
          Soglia di durata
        </label>
        <input
          id="receiver-edit-duration-threshold"
          type="number"
          min={1}
          placeholder="nessuna"
          value={durationAmount}
          onChange={(event) => setDurationAmount(event.target.value)}
        />
        <select
          aria-label="Unita della soglia di durata"
          value={durationUnit}
          onChange={(event) =>
            setDurationUnit(event.target.value as DurationUnit)
          }
        >
          {DURATION_UNITS.map((unit) => (
            <option key={unit} value={unit}>
              {DURATION_UNIT_LABELS[unit]}
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="receiver-edit-duration-severity">
          Severity oltre la soglia di durata
        </label>
        <select
          id="receiver-edit-duration-severity"
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
      </div>
      <fieldset
        style={{
          border: "1px solid var(--color-border)",
          borderRadius: 6,
          padding: 12,
        }}
      >
        <legend>Sorveglianza dell'attesa</legend>
        <p className="card-hint">
          Notifica quando un invio <strong>non</strong> arriva: macchina spenta,
          cron rimosso, rete verso NotifyHub assente. Se il job usa{" "}
          <code>--only-on-failure</code> non va sorvegliato cosi': un'esecuzione
          riuscita non manda niente e verrebbe segnalata come assenza.
        </p>
        <div className="form-row">
          <label htmlFor="receiver-edit-expected-mode">Attesa</label>
          <select
            id="receiver-edit-expected-mode"
            value={expectedMode}
            onChange={(event) =>
              setExpectedMode(event.target.value as ExpectedMode)
            }
          >
            {(Object.keys(EXPECTED_MODE_LABELS) as ExpectedMode[]).map(
              (mode) => (
                <option key={mode} value={mode}>
                  {EXPECTED_MODE_LABELS[mode]}
                </option>
              ),
            )}
          </select>
        </div>

        {expectedMode === "interval" && (
          <div className="form-row">
            <label htmlFor="receiver-edit-expected-interval">
              Mi aspetto un invio ogni
            </label>
            <input
              id="receiver-edit-expected-interval"
              type="number"
              min={1}
              value={intervalAmount}
              onChange={(event) => setIntervalAmount(event.target.value)}
            />
            <select
              aria-label="Unita dell'intervallo atteso"
              value={intervalUnit}
              onChange={(event) =>
                setIntervalUnit(event.target.value as DurationUnit)
              }
            >
              {DURATION_UNITS.map((unit) => (
                <option key={unit} value={unit}>
                  {DURATION_UNIT_LABELS[unit]}
                </option>
              ))}
            </select>
          </div>
        )}

        {expectedMode === "cron" && (
          <>
            <div className="form-row">
              <label htmlFor="receiver-edit-expected-cron">
                Espressione cron
              </label>
              <input
                id="receiver-edit-expected-cron"
                placeholder="0 3 * * 1-5"
                value={cron}
                onChange={(event) => setCron(event.target.value)}
              />
            </div>
            <div className="form-row">
              <label htmlFor="receiver-edit-expected-timezone">
                Fuso dell'espressione
              </label>
              <input
                id="receiver-edit-expected-timezone"
                list="receiver-timezones"
                placeholder="UTC"
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
              />
              <datalist id="receiver-timezones">
                {knownTimezones().map((zone) => (
                  <option key={zone} value={zone} />
                ))}
              </datalist>
            </div>
            <p className="card-hint">
              La stessa riga che sta nel crontab della macchina, con il fuso in
              cui quella macchina la interpreta.
            </p>
          </>
        )}

        {expectedMode !== "off" && (
          <>
            <div className="form-row">
              <label htmlFor="receiver-edit-expected-grace">
                Tolleranza sul ritardo
              </label>
              <input
                id="receiver-edit-expected-grace"
                type="number"
                min={0}
                value={graceAmount}
                onChange={(event) => setGraceAmount(event.target.value)}
              />
              <select
                aria-label="Unita della tolleranza"
                value={graceUnit}
                onChange={(event) =>
                  setGraceUnit(event.target.value as DurationUnit)
                }
              >
                {DURATION_UNITS.map((unit) => (
                  <option key={unit} value={unit}>
                    {DURATION_UNIT_LABELS[unit]}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-row">
              <label htmlFor="receiver-edit-missing-severity">
                Severity dell'assenza
              </label>
              <select
                id="receiver-edit-missing-severity"
                value={missingSeverity}
                onChange={(event) =>
                  setMissingSeverity(event.target.value as Severity)
                }
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
      </fieldset>

      {formError && (
        <p className="error-banner" role="alert">
          {formError}
        </p>
      )}
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

function DownloadWrapperButton({ receiver }: { receiver: ReceiverOut }) {
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function download() {
    setError(null);
    setBusy(true);
    try {
      // Il file arriva dal backend gia' compilato: URL pubblica dell'istanza e
      // slug di questo receiver. Ricostruirlo qui vorrebbe dire indovinare
      // l'URL dal browser e rischiare che i due non coincidano.
      const { content, filename } = await apiGetFile(
        `/api/v1/receivers/${receiver.id}/wrapper-script`,
        "notifyhub-run.sh",
      );
      const url = URL.createObjectURL(
        new Blob([content], { type: "text/x-shellscript" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error && <ErrorBanner error={error} />}
      <button onClick={() => void download()} disabled={busy}>
        {busy ? "Preparazione…" : "Scarica lo script"}
      </button>
    </div>
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
          <p>
            Verranno eliminate anche le notifiche e le consegne collegate a
            questo receiver.
          </p>
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

  const {
    data: receiver,
    isLoading,
    error,
  } = useQuery<ReceiverOut, ApiError>({
    queryKey: ["receiver", id],
    queryFn: () => apiGet<ReceiverOut>(`/api/v1/receivers/${id}`),
    enabled: Boolean(id),
  });

  if (isLoading) return <p>Caricamento…</p>;
  if (error) return <ErrorBanner error={error} />;
  if (!receiver) return null;

  const canManage = hasRole(role, MEMBER_ROLES);
  // URL dal backend, non da window.location: e' la stessa che finisce nello
  // script scaricabile, quindi i due non possono divergere dietro reverse proxy.
  const curlCommand = `curl --data "corpo del messaggio" ${receiver.ingest_url}`;

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
          <EditReceiverForm
            receiver={receiver}
            onDone={() => setEditing(false)}
          />
        ) : (
          <>
            <p>
              Slug: <code>{receiver.slug}</code>{" "}
              <button onClick={() => void copySlug()}>
                {copied ? "Copiato!" : "Copia"}
              </button>
            </p>
            <p>
              URL di invio: <code>{receiver.ingest_url}</code>
            </p>
            <p>
              <code>{curlCommand}</code>
            </p>
            <p className="card-hint">
              Per i job da crontab: <code>notifyhub-run.sh</code> con URL e slug
              gia' compilati, scritti in due variabili in cima al file e
              modificabili a mano.
            </p>
            <p>Stato: {receiver.status}</p>
            <p>Severity di default: {receiver.default_severity}</p>
            <p>
              Severity per exit code diverso da zero:{" "}
              {receiver.exit_code_severity ?? "nessun effetto"}
            </p>
            <p>
              Soglia di durata:{" "}
              {receiver.duration_threshold_seconds !== null &&
              receiver.duration_severity !== null
                ? `oltre ${formatDurationSeconds(receiver.duration_threshold_seconds)} → ${receiver.duration_severity}`
                : "nessun effetto"}
            </p>
            <p>Sorveglianza dell'attesa: {describeExpectation(receiver)}</p>
            {receiver.missing_severity !== null && (
              <p className="card-hint">
                Ultimo invio: {formatInstant(receiver.last_notification_at)} ·
                Allarme se non arriva entro{" "}
                {formatInstant(receiver.expected_deadline_at)}
              </p>
            )}
            {receiver.expected_late && (
              <div className="error-banner" role="alert">
                In ritardo: nessun invio entro la scadenza.
                {receiver.missing_alerted_at !== null
                  ? ` Assenza segnalata il ${formatInstant(receiver.missing_alerted_at)}.`
                  : " La notifica di assenza parte al prossimo controllo (entro un minuto)."}
              </div>
            )}
            <p>Limite corpo: {receiver.max_body_bytes} byte</p>
            <p>Rate limit: {receiver.rate_limit_per_min}/min</p>
            {receiver.status === "disabled" && (
              <div className="error-banner">
                {receiver.rejected_last_24h ?? 0} richieste rifiutate nelle
                ultime 24 ore.
              </div>
            )}
            <div className="toolbar">
              <DownloadWrapperButton receiver={receiver} />
              {hasRole(role, ADMIN_ROLES) && (
                <button onClick={() => void doRotate()}>Rigenera slug</button>
              )}
              {canManage && (
                <button onClick={() => setEditing(true)}>
                  Modifica receiver
                </button>
              )}
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
