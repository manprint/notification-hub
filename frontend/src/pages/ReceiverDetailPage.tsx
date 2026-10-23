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
  INT4_MAX,
  formatDurationSeconds,
  formatIntervalSeconds,
  maxAmount,
  parseDurationInput,
  parseIntegerInput,
  splitDuration,
} from "../lib/duration";
import { saveBlob } from "../lib/download";
import { formatBytes, formatInstantOr } from "../lib/format";
import { invalidateReceiverLists } from "../lib/receiverCache";
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

/** I cinque campi della sorveglianza come li scrive la PATCH. */
interface ExpectedPayload {
  expected_every_seconds: number | null;
  expected_cron: string | null;
  expected_timezone: string | null;
  expected_grace_seconds: number | null;
  missing_severity: Severity | null;
}

/** La politica salvata, con il fuso come lo valuta il backend: un cron senza
 *  fuso e' un cron in UTC, quindi "UTC" scritto nel form non e' una modifica. */
function storedExpectation(receiver: ReceiverOut): ExpectedPayload {
  return {
    expected_every_seconds: receiver.expected_every_seconds,
    expected_cron: receiver.expected_cron,
    expected_timezone:
      receiver.expected_cron !== null ? (receiver.expected_timezone ?? DEFAULT_TIMEZONE) : null,
    expected_grace_seconds: receiver.expected_grace_seconds,
    missing_severity: receiver.missing_severity,
  };
}

function sameExpectation(a: ExpectedPayload, b: ExpectedPayload): boolean {
  return (
    a.expected_every_seconds === b.expected_every_seconds &&
    a.expected_cron === b.expected_cron &&
    a.expected_timezone === b.expected_timezone &&
    a.expected_grace_seconds === b.expected_grace_seconds &&
    a.missing_severity === b.missing_severity
  );
}

/** Fuso da preselezionare. Con un cron gia' salvato vale il fuso salvato, e se
 *  manca UTC: e' come lo valuta il backend. Proporre il fuso del browser a un
 *  cron salvato senza fuso vorrebbe dire spostarlo di qualche ora al primo
 *  salvataggio, senza che nessuno l'abbia chiesto. Il fuso del browser resta il
 *  suggerimento per chi il cron lo sta scrivendo adesso. */
function initialTimezone(receiver: ReceiverOut): string {
  if (receiver.expected_cron !== null) return receiver.expected_timezone ?? DEFAULT_TIMEZONE;
  return browserTimezone() ?? DEFAULT_TIMEZONE;
}

type FieldKey = "body" | "rate" | "duration" | "interval" | "grace";

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
  // Lo stato letto all'apertura del form: la PATCH manda solo ciò che l'utente
  // ha cambiato rispetto a questo, non il receiver com'è adesso sul server.
  // Rimandare i campi non toccati riscriverebbe una modifica fatta da un altro
  // nel frattempo (severity di default, soglia, exit code...).
  const [initial] = useState(receiver);
  const [name, setName] = useState(receiver.name);
  const [defaultSeverity, setDefaultSeverity] = useState<Severity>(receiver.default_severity);
  // Testo e non numero: con `Number(value)` nello stato, svuotare il campo lo
  // faceva diventare 0 e il rate limit vuoto si salvava come "nessun limite".
  const [maxBodyBytes, setMaxBodyBytes] = useState(String(receiver.max_body_bytes));
  const [rateLimitPerMin, setRateLimitPerMin] = useState(String(receiver.rate_limit_per_min));
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
  const [timezone, setTimezone] = useState(() => initialTimezone(receiver));
  const initialGrace = splitDuration(receiver.expected_grace_seconds ?? DEFAULT_GRACE_SECONDS);
  const [graceAmount, setGraceAmount] = useState(initialGrace.amount);
  const [graceUnit, setGraceUnit] = useState<DurationUnit>(initialGrace.unit);
  const [missingSeverity, setMissingSeverity] = useState<Severity>(
    receiver.missing_severity ?? "critical",
  );
  const [nameError, setNameError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});

  // Validazione dell'espressione cron mentre si scrive: bloccante al salvataggio
  // e mostrata sotto il campo. Vale solo nel modo cron.
  const cronError = expectedMode === "cron" ? validateCronExpression(cron) : null;
  // Prossime tre occorrenze, solo per un cron valido nel fuso scelto.
  const nextExecutions =
    expectedMode === "cron" && cronError === null
      ? nextCronExecutions(cron.trim(), timezone.trim() || "UTC")
      : [];

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    // Ogni campo numerico si controlla qui, prima della richiesta: vuoto,
    // decimale, infinito (`1e308`) o oltre il massimo intero del backend
    // (2147483647, dopo la conversione in secondi) hanno un messaggio sul campo
    // invece di un 422 generico, o peggio di un valore salvato per sbaglio.
    const errors: Partial<Record<FieldKey, string>> = {};
    const body = parseIntegerInput(maxBodyBytes, {
      min: 1,
      empty: "Indica il limite del corpo in byte.",
    });
    if (!body.ok) errors.body = body.error;
    const rate = parseIntegerInput(rateLimitPerMin, {
      min: 0,
      empty: "Indica il rate limit: 0 se non vuoi nessun limite.",
    });
    if (!rate.ok) errors.rate = rate.error;

    const hasAmount = durationAmount.trim() !== "";
    let thresholdSeconds: number | null = null;
    if (hasAmount) {
      const threshold = parseDurationInput(durationAmount, durationUnit, { minSeconds: 1 });
      if (threshold.ok) thresholdSeconds = threshold.value;
      else errors.duration = threshold.error;
    }

    let intervalSeconds: number | null = null;
    if (expectedMode === "interval") {
      const interval = parseDurationInput(intervalAmount, intervalUnit, {
        minSeconds: 1,
        empty: "Indica ogni quanto ti aspetti un invio.",
      });
      if (interval.ok) intervalSeconds = interval.value;
      else errors.interval = interval.error;
    }
    let graceSeconds: number | null = null;
    if (expectedMode !== "off") {
      const grace = parseDurationInput(graceAmount, graceUnit, {
        minSeconds: 0,
        empty: "Indica la tolleranza sul ritardo (anche zero, se il job è puntuale).",
      });
      if (grace.ok) graceSeconds = grace.value;
      else errors.grace = grace.error;
    }

    const nameMissing = name.trim() === "";
    setNameError(nameMissing ? "Il nome del receiver è obbligatorio." : null);
    setFieldErrors(errors);
    if (nameMissing || Object.keys(errors).length > 0 || !body.ok || !rate.ok) return;

    // Soglia e severity vanno insieme: il backend rifiuta con 422 la coppia
    // mezza configurata, ma dirlo qui costa un giro di rete in meno e spiega
    // meglio quale dei due campi manca.
    const hasSeverity = durationSeverity !== DURATION_DISABLED;
    if (hasAmount !== hasSeverity) {
      setFormError(
        hasAmount
          ? "Scegli la severity da applicare oltre la soglia di durata, o svuota la soglia."
          : "Imposta una soglia di durata maggiore di zero, o riporta la severity a «nessun effetto».",
      );
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

    const expected: ExpectedPayload =
      expectedMode === "off"
        ? {
            expected_every_seconds: null,
            expected_cron: null,
            expected_timezone: null,
            expected_grace_seconds: null,
            missing_severity: null,
          }
        : {
            expected_every_seconds: intervalSeconds,
            expected_cron: expectedMode === "cron" ? cron.trim() : null,
            expected_timezone: expectedMode === "cron" ? timezone.trim() || "UTC" : null,
            expected_grace_seconds: graceSeconds,
            missing_severity: missingSeverity,
          };
    // La sorveglianza si manda solo se e' cambiata. La PATCH distingue il campo
    // omesso (resta quello salvato) dal null (spegne), e il backend rivaluta la
    // politica appena uno dei cinque campi e' presente: rimandarli uguali a
    // ogni rinomina riscriverebbe il fuso di un cron salvato senza fuso e
    // farebbe fallire il salvataggio di un nome per un cron salvato con regole
    // piu' vecchie di quelle attuali.
    const expectedChanges = sameExpectation(expected, storedExpectation(initial)) ? {} : expected;
    // null e' un valore, non "campo assente": disattiva la politica.
    const exitCodeValue = exitCodeSeverity === EXIT_CODE_DISABLED ? null : exitCodeSeverity;
    const durationSeverityValue = hasSeverity ? durationSeverity : null;
    const fieldChanges = {
      ...(name.trim() !== initial.name ? { name: name.trim() } : {}),
      ...(defaultSeverity !== initial.default_severity
        ? { default_severity: defaultSeverity }
        : {}),
      ...(body.value !== initial.max_body_bytes ? { max_body_bytes: body.value } : {}),
      ...(rate.value !== initial.rate_limit_per_min
        ? { rate_limit_per_min: rate.value }
        : {}),
      ...(exitCodeValue !== initial.exit_code_severity
        ? { exit_code_severity: exitCodeValue }
        : {}),
      ...(thresholdSeconds !== initial.duration_threshold_seconds
        ? { duration_threshold_seconds: thresholdSeconds }
        : {}),
      ...(durationSeverityValue !== initial.duration_severity
        ? { duration_severity: durationSeverityValue }
        : {}),
    };

    const ok = await run(
      async () => {
        await apiPatch(`/api/v1/receivers/${receiver.id}`, {
          ...fieldChanges,
          ...expectedChanges,
        });
        await queryClient.invalidateQueries({ queryKey: ["receiver", receiver.id] });
        // Nome e stato compaiono negli elenchi; severity di default, exit code e
        // soglia di durata cambiano il risultato della prova sulle notifiche
        // gia' arrivate.
        await invalidateReceiverLists(queryClient, receiver.group_id);
        await queryClient.invalidateQueries({ queryKey: ["severity-replay", receiver.id] });
      },
      { success: "Impostazioni del receiver salvate." },
    );
    if (ok) onDone();
  }

  return (
    // noValidate: i controlli li fa handleSubmit, con messaggi in italiano sul
    // campo giusto, invece del fumetto del browser (diverso per ogni browser e
    // muto su valori come 1e308).
    <form noValidate onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <RequiredLegend />

      <div className="form-grid">
        <Field id="receiver-edit-name" label="Nome" required error={nameError}>
          <input
            {...fieldAria("receiver-edit-name", { error: nameError })}
            required
            maxLength={255}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="receiver-edit-severity" label="Severity di default" required>
          <select
            {...fieldAria("receiver-edit-severity")}
            required
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
        <Field
          id="receiver-edit-body"
          label="Limite corpo (byte)"
          required
          error={fieldErrors.body}
        >
          <input
            {...fieldAria("receiver-edit-body", { error: fieldErrors.body })}
            type="number"
            min={1}
            max={INT4_MAX}
            required
            value={maxBodyBytes}
            onChange={(event) => setMaxBodyBytes(event.target.value)}
          />
        </Field>
        <Field
          id="receiver-edit-rate"
          label="Rate limit (al minuto)"
          required
          error={fieldErrors.rate}
          hint="Invii accettati al minuto su questo receiver: oltre, risposta 429. 0 = nessun limite."
        >
          <input
            {...fieldAria("receiver-edit-rate", { hint: true, error: fieldErrors.rate })}
            type="number"
            min={0}
            max={INT4_MAX}
            required
            value={rateLimitPerMin}
            onChange={(event) => setRateLimitPerMin(event.target.value)}
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
          <Field
            id="receiver-edit-duration-threshold"
            label="Soglia di durata"
            error={fieldErrors.duration}
          >
            <div className="input-with-unit">
              <input
                {...fieldAria("receiver-edit-duration-threshold", { error: fieldErrors.duration })}
                type="number"
                min={1}
                max={maxAmount(durationUnit)}
                step="any"
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
            required
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
          <Field
            id="receiver-edit-expected-interval"
            label="Mi aspetto un invio ogni"
            required
            error={fieldErrors.interval}
          >
            <div className="input-with-unit">
              <input
                {...fieldAria("receiver-edit-expected-interval", { error: fieldErrors.interval })}
                type="number"
                min={1}
                max={maxAmount(intervalUnit)}
                step="any"
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
                  required
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
              error={fieldErrors.grace}
              hint="Quanto si aspetta dopo l'orario previsto prima di gridare."
            >
              <div className="input-with-unit">
                <input
                  {...fieldAria("receiver-edit-expected-grace", {
                    hint: true,
                    error: fieldErrors.grace,
                  })}
                  type="number"
                  min={0}
                  max={maxAmount(graceUnit)}
                  step="any"
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
                required
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
      // saveBlob e non un'ancora fatta qui: revocare l'URL subito dopo il click
      // fa fallire lo scaricamento su Firefox e Safari, che lo avviano in modo
      // asincrono.
      saveBlob(new Blob([content], { type: "text/x-shellscript" }), filename);
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
  // Una pagina per receiver. Passando da un receiver all'altro (Indietro e
  // Avanti del browser, un link) React riusava lo stesso componente: il modulo
  // di modifica restava aperto con i valori del receiver precedente e il
  // salvataggio li scriveva sul nuovo. Con la key tutto lo stato locale
  // (modifica aperta, conferme, esito delle azioni) riparte da zero.
  return <ReceiverDetail key={id} id={id} />;
}

function ReceiverDetail({ id }: { id: string | undefined }) {
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
        await refreshReceiver();
      },
      { name: "rotate", success: "Slug rigenerato: aggiorna i job che inviano qui." },
    );
  }

  async function toggleStatus(disable: boolean) {
    setConfirming(null);
    await run(
      async () => {
        await apiPatch(`/api/v1/receivers/${id}`, { status: disable ? "disabled" : "active" });
        await refreshReceiver();
      },
      {
        name: "status",
        success: disable
          ? "Receiver disabilitato: gli invii verranno rifiutati."
          : "Receiver riattivato: la sorveglianza riparte da adesso.",
      },
    );
  }

  /** La pagina del receiver e ogni elenco in cui compare: nome, stato e slug
   *  si leggono anche nella pagina del gruppo e nelle notifiche. */
  async function refreshReceiver() {
    await queryClient.invalidateQueries({ queryKey: ["receiver", id] });
    if (receiver) await invalidateReceiverLists(queryClient, receiver.group_id);
  }

  async function removeReceiver() {
    setConfirming(null);
    if (!receiver) return;
    const groupId = receiver.group_id;
    const ok = await run(async () => apiDelete(`/api/v1/receivers/${id}`), {
      name: "delete",
      success: "Receiver eliminato.",
    });
    if (!ok) return;
    // Si torna al gruppo da cui si era arrivati, non all'elenco dei gruppi.
    navigate(`/groups/${groupId}`, { replace: true });
    // Il receiver sparisce dagli elenchi e con lui le sue notifiche.
    void invalidateReceiverLists(queryClient, groupId);
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
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
          {disabled && <span className="status-pill warn">Disabilitato</span>}
        </h1>
        {!editing && (
          <div className="page-header-actions">
            {canManage && (
              <button className="primary" onClick={() => setEditing(true)}>
                Modifica receiver
              </button>
            )}
            <DownloadWrapperButton key={receiver.id} receiver={receiver} />
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
            <h3>Modifica receiver</h3>
          </div>
          <EditReceiverForm
            key={receiver.id}
            receiver={receiver}
            onDone={() => setEditing(false)}
          />
        </div>
      ) : (
        <>
          <div className="card">
            <div className="card-header">
              <h3>Come inviare qui</h3>
            </div>
            <div className="detail-grid">
              <Detail label="Slug" wide>
                <span className="copy-field">
                  <code>{receiver.slug}</code>
                  <CopyButton value={receiver.slug} label="Copia slug" />
                </span>
              </Detail>
              <Detail label="URL di invio" wide>
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
              <div className="warning-banner" role="status">
                Receiver disabilitato: {receiver.rejected_last_24h ?? 0}{" "}
                {(receiver.rejected_last_24h ?? 0) === 1 ? "richiesta rifiutata" : "richieste rifiutate"}{" "}
                nelle ultime 24 ore.
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <h3>Configurazione</h3>
            </div>
            <div className="detail-grid">
              <Detail label="Stato del receiver">
                <span className={`status-pill ${disabled ? "warn" : "ok"}`}>
                  {disabled ? "Disabilitato" : "Attivo"}
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
              <h3>Sorveglianza dell'attesa</h3>
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

      {/* key: stato interno (esito della prova, conferme, modifica di una
          regola) legato a questo receiver, mai ereditato da un altro. */}
      <ReceiverPresetsPanel key={`presets-${receiver.id}`} receiverId={receiver.id} />
      <SeverityRulesPanel key={`rules-${receiver.id}`} receiver={receiver} />

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
          title={`Elimina receiver «${receiver.name}»`}
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
