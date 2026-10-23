import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPatch } from "../api/client";
import type { ApiError, TenantOut } from "../api/types";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import Field, { fieldAria } from "../components/Field";
import SettingsTabs from "../components/SettingsTabs";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { formatBytes } from "../lib/format";
import { INT4_MAX } from "../lib/duration";

interface ConflictingReceiver {
  name: string;
  max_body_bytes: number;
}

/** Tetto del backend per il cap corpo (TenantUpdate.max_body_bytes, 20 MiB). */
const MAX_BODY_BYTES_LIMIT = 20_971_520;

/** Il massimo di un campo: il numero per il controllo del modulo e l'attributo
 *  `max`, e il testo esatto per il confronto (oltre 2^53 il numero arrotonda). */
interface Limite {
  max: number;
  testo: string;
  /** Messaggio proprio, se il generico "Il massimo è …" non dice abbastanza. */
  messaggio?: string;
}

/** Colonne integer di PostgreSQL: retention e quote giornaliere (schemas/tenant.py). */
const LIMITE_INT4: Limite = { max: INT4_MAX, testo: String(INT4_MAX) };
/** Colonna BIGINT: lo spazio massimo in byte (schemas/tenant.py, BIGINT_MAX).
 *  Il JSON parte da un numero JS, esatto solo fino a 2^53-1: oltre il valore
 *  verrebbe arrotondato (9223372036854775807 partirebbe come ...776000 e il
 *  backend lo rifiuterebbe). Il tetto del campo qui è quindi 2^53-1. */
const LIMITE_BIGINT: Limite = {
  max: Number.MAX_SAFE_INTEGER,
  testo: String(Number.MAX_SAFE_INTEGER),
};
/** Il cap corpo: il tetto del backend (TenantUpdate.max_body_bytes). */
const LIMITE_CAP: Limite = {
  max: MAX_BODY_BYTES_LIMIT,
  testo: String(MAX_BODY_BYTES_LIMIT),
  messaggio: `Il cap non può superare ${formatBytes(MAX_BODY_BYTES_LIMIT)} (${MAX_BODY_BYTES_LIMIT} byte).`,
};

/** Le quote per cui null vuol dire "illimitata" (contratto di PATCH /tenant:
 *  null esplicito toglie il limite, campo omesso lo lascia com'è). */
type LimitKey =
  | "retention_days"
  | "max_notifications_per_day"
  | "max_storage_bytes"
  | "audit_retention_days";

type FieldKey = LimitKey | "max_body_bytes";

interface LimitField {
  key: LimitKey;
  id: string;
  label: string;
  hint: string;
  /** Etichetta della spunta: dice quale limite toglie, perché le spunte sono
   *  quattro una sotto l'altra. */
  unlimitedLabel: string;
  /** Nome breve nel riquadro dei valori in vigore. */
  summary: string;
  /** Il massimo che il backend accetta per questo campo. */
  limite: Limite;
  current: (tenant: TenantOut) => string;
}

const LIMIT_FIELDS: LimitField[] = [
  {
    key: "retention_days",
    summary: "Retention notifiche",
    id: "retention-days",
    label: "Retention (giorni)",
    hint: "Dopo quanti giorni le notifiche vengono cancellate dal job notturno.",
    unlimitedLabel: "Notifiche senza scadenza",
    limite: LIMITE_INT4,
    current: (t) => (t.retention_days === null ? "illimitata" : `${t.retention_days} giorni`),
  },
  {
    key: "max_notifications_per_day",
    summary: "Quota giornaliera",
    id: "max-notifications",
    label: "Quota giornaliera notifiche",
    hint: "Superata la quota, l'ingestion risponde 429 fino al giorno dopo.",
    unlimitedLabel: "Nessuna quota giornaliera",
    limite: LIMITE_INT4,
    current: (t) =>
      t.max_notifications_per_day === null
        ? "illimitata"
        : `${t.max_notifications_per_day} notifiche`,
  },
  {
    key: "max_storage_bytes",
    summary: "Spazio massimo",
    id: "max-storage-bytes",
    label: "Spazio massimo (byte)",
    hint: "Somma dei corpi delle notifiche conservate: oltre, l'ingestion risponde 429.",
    unlimitedLabel: "Spazio illimitato",
    limite: LIMITE_BIGINT,
    current: (t) => (t.max_storage_bytes === null ? "illimitato" : formatBytes(t.max_storage_bytes)),
  },
  {
    key: "audit_retention_days",
    summary: "Retention audit",
    id: "audit-retention-days",
    label: "Retention audit (giorni)",
    hint: "Separata dalla retention delle notifiche: l'audit deve poter raccontare chi ha gestito una notifica anche dopo che la notifica è stata cancellata.",
    unlimitedLabel: "Audit senza scadenza",
    limite: LIMITE_INT4,
    current: (t) =>
      t.audit_retention_days === null ? "illimitata" : `${t.audit_retention_days} giorni`,
  },
];

const NOT_A_COUNT = "Serve un numero intero maggiore di zero.";

/** Un intero fra 1 e il massimo del campo, o il messaggio da mostrare sotto
 *  il campo. Il massimo sta qui, non solo nel backend: un valore fuori scala
 *  arriverebbe come 422 in inglese (o come 500 oltre il bigint). */
function parseCount(raw: string, limite: Limite = LIMITE_INT4): number | string {
  // Gli zeri in testa non sono cifre: "0000…01" vale 1.
  const text = raw.trim().replace(/^0+(?=\d)/, "");
  const value = Number(text);
  if (!Number.isInteger(value) || value < 1) return NOT_A_COUNT;
  // Confronto sulle cifre, non sul numero: oltre 2^53 Number arrotonda e un
  // valore appena sopra il massimo passerebbe.
  const piuLungo = text.length > limite.testo.length;
  const stessaLunghezzaPiuGrande =
    text.length === limite.testo.length && /^\d+$/.test(text) && text > limite.testo;
  if (value > limite.max || piuLungo || stessaLunghezzaPiuGrande) {
    return limite.messaggio ?? `Il massimo è ${limite.testo}.`;
  }
  return value;
}

/** Toglie da `current` le voci uguali a quelle inviate: quelle cambiate mentre
 *  la richiesta era in volo restano dove le ha scritte chi le ha scritte. */
function without<T>(
  current: Partial<Record<LimitKey, T>>,
  sent: Partial<Record<LimitKey, T>>,
): Partial<Record<LimitKey, T>> {
  const next = { ...current };
  for (const key of Object.keys(sent) as LimitKey[]) {
    if (next[key] === sent[key]) delete next[key];
  }
  return next;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { role } = useSession();
  const {
    data: tenant,
    isLoading,
    error: tenantError,
  } = useQuery<TenantOut, ApiError>({
    queryKey: ["tenant"],
    queryFn: () => apiGet<TenantOut>("/api/v1/tenant"),
  });

  const [maxBodyBytes, setMaxBodyBytes] = useState<string>("");
  const [values, setValues] = useState<Partial<Record<LimitKey, string>>>({});
  // Solo le spunte toccate: quelle non toccate seguono il valore in vigore,
  // così una quota già illimitata si presenta spuntata.
  const [unlimited, setUnlimited] = useState<Partial<Record<LimitKey, boolean>>>({});
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [conflicting, setConflicting] = useState<ConflictingReceiver[] | null>(null);
  const { busy, error, run } = useAction();

  function isUnlimited(current: TenantOut, key: LimitKey): boolean {
    return unlimited[key] ?? current[key] === null;
  }

  /** Il corpo della PATCH con i soli campi cambiati, o gli errori per campo. */
  function buildPatch(current: TenantOut) {
    const body: Partial<Record<FieldKey, number | null>> = {};
    const errors: Partial<Record<FieldKey, string>> = {};

    if (maxBodyBytes !== "") {
      const parsed = parseCount(maxBodyBytes, LIMITE_CAP);
      if (typeof parsed === "string") errors.max_body_bytes = parsed;
      else body.max_body_bytes = parsed;
    }

    for (const field of LIMIT_FIELDS) {
      const inForce = current[field.key];
      if (isUnlimited(current, field.key)) {
        // null esplicito: è l'unico modo di tornare a "illimitata". Se lo è già
        // non si manda niente, come per un campo lasciato vuoto.
        if (inForce !== null) body[field.key] = null;
        continue;
      }
      const raw = values[field.key] ?? "";
      if (raw === "") {
        // Spunta tolta a una quota illimitata senza dire quale limite mettere.
        if (inForce === null) errors[field.key] = "Indica un limite, o rimetti la spunta.";
        continue;
      }
      const parsed = parseCount(raw, field.limite);
      if (typeof parsed === "string") errors[field.key] = parsed;
      else body[field.key] = parsed;
    }
    return { body, errors };
  }

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tenant) return;
    setConflicting(null);
    const { body, errors } = buildPatch(tenant);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    // Ciò che è partito con la richiesta: a salvataggio riuscito si pulisce solo
    // questo, non quello che chi scrive ha digitato nel frattempo.
    const inviato = { maxBodyBytes, values, unlimited };

    const ok = await run(
      async () => {
        try {
          await apiPatch("/api/v1/tenant", body);
        } catch (err) {
          // Il rifiuto per i receiver che sforano porta con sé l'elenco: va
          // mostrato per esteso, non riassunto in "conflitto".
          const receivers = (err as ApiError).extra?.conflicting_receivers;
          if (Array.isArray(receivers)) setConflicting(receivers as ConflictingReceiver[]);
          throw err;
        }
        await queryClient.invalidateQueries({ queryKey: ["tenant"] });
      },
      { success: "Impostazioni del tenant salvate." },
    );
    // A salvataggio riuscito i campi tornano vuoti e le spunte seguono di nuovo
    // il valore in vigore: lasciare il numero digitato farebbe credere che ci
    // sia ancora una modifica in sospeso.
    if (ok) {
      setMaxBodyBytes((current) => (current === inviato.maxBodyBytes ? "" : current));
      setValues((current) => without(current, inviato.values));
      setUnlimited((current) => without(current, inviato.unlimited));
    }
  }

  // La pagina ha la sua cornice anche mentre carica o se la lettura fallisce:
  // senza, un errore lascerebbe una pagina vuota, senza titolo né schede.
  const cornice = (
    <>
      <div className="page-header">
        <h1>Impostazioni</h1>
      </div>
      <SettingsTabs />
    </>
  );
  if (isLoading)
    return (
      <div>
        {cornice}
        <EmptyState message="Caricamento…" />
      </div>
    );
  if (!tenant)
    return (
      <div>
        {cornice}
        {tenantError && <ErrorBanner error={tenantError} />}
      </div>
    );

  // Le quote del tenant restano una decisione dell'owner: un admin arriva qui
  // per l'audit, e vede le schede ma non il modulo (backend: require_owner su
  // PATCH /api/v1/tenant).
  // `role === null` significa sessione non ancora risolta, non "ruolo
  // insufficiente": nasconderle il modulo la farebbe sparire per un istante a
  // ogni caricamento. Il rifiuto vero lo dà comunque il backend.
  if (role !== null && role !== "owner") {
    return (
      <div>
        <div className="page-header">
          <h1>Impostazioni</h1>
        </div>
        <SettingsTabs />
        <p className="page-subtitle">
          Le impostazioni generali sono riservate all'owner. Le schede Audit e Letture e verifiche
          sono accessibili anche agli admin.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h1>Impostazioni</h1>
      </div>
      <SettingsTabs />
      {error && <ErrorBanner error={error} />}
      {conflicting && (
        <div className="error-banner">
          <p>Questi receiver hanno un limite superiore a quello richiesto:</p>
          <ul className="error-details">
            {/* Il nome non è unico (due receiver "backup" in gruppi diversi): la
                posizione nell'elenco è la chiave, il nome solo testo. */}
            {conflicting.map((r, index) => (
              <li key={`${index}-${r.name}`}>
                {r.name}: {formatBytes(r.max_body_bytes)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <h3>Valori in vigore</h3>
          <span className="card-header-actions text-muted text-sm">{tenant.name}</span>
        </div>
        <div className="detail-grid">
          <div>
            <span className="detail-label">Cap corpo</span>
            <p className="detail-value" title={`${tenant.max_body_bytes} byte`}>
              {formatBytes(tenant.max_body_bytes)}
            </p>
          </div>
          {LIMIT_FIELDS.map((field) => (
            <div key={field.key}>
              <span className="detail-label">{field.summary}</span>
              <p className="detail-value">{field.current(tenant)}</p>
            </div>
          ))}
        </div>
      </div>

      {/* noValidate: i limiti (intero, massimo del cap) li controlla il modulo e
          li dice sotto il campo, come nel resto dell'interfaccia; il fumetto del
          browser comparirebbe prima e con un altro testo. */}
      <form onSubmit={(event) => void handleSubmit(event)} className="card" noValidate>
        <div className="card-header">
          <h3>Modifica le quote</h3>
        </div>
        <p className="card-hint">
          Un campo lasciato vuoto non cambia il valore in vigore: si compila solo ciò che si vuole
          modificare. La spunta sotto un campo toglie il limite.
        </p>
        <div className="form-grid">
          <Field
            id="max-body-bytes"
            label="Cap corpo (byte)"
            optional
            error={fieldErrors.max_body_bytes}
            hint={`In vigore: ${formatBytes(tenant.max_body_bytes)}. Nessun receiver può superarlo; al massimo ${formatBytes(MAX_BODY_BYTES_LIMIT)}.`}
          >
            <input
              {...fieldAria("max-body-bytes", { hint: true, error: fieldErrors.max_body_bytes })}
              type="number"
              min={1}
              max={MAX_BODY_BYTES_LIMIT}
              step={1}
              value={maxBodyBytes}
              onChange={(event) => setMaxBodyBytes(event.target.value)}
            />
          </Field>
          {LIMIT_FIELDS.map((field) => {
            const off = isUnlimited(tenant, field.key);
            const fieldError = fieldErrors[field.key];
            return (
              <Field
                key={field.key}
                id={field.id}
                label={field.label}
                optional
                error={fieldError}
                hint={`In vigore: ${field.current(tenant)}. ${field.hint}`}
              >
                <input
                  {...fieldAria(field.id, { hint: true, error: fieldError })}
                  type="number"
                  min={1}
                  max={field.limite.max}
                  step={1}
                  disabled={off}
                  // Il valore in vigore sta nella suggestione sopra il campo: il
                  // placeholder non deve sembrare un valore già scritto.
                  placeholder={off ? "senza limite" : undefined}
                  value={off ? "" : (values[field.key] ?? "")}
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [field.key]: event.target.value }))
                  }
                />
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={off}
                    onChange={(event) =>
                      setUnlimited((prev) => ({ ...prev, [field.key]: event.target.checked }))
                    }
                  />
                  {field.unlimitedLabel}
                </label>
              </Field>
            );
          })}
        </div>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Salvataggio…" : "Salva"}
          </button>
        </div>
      </form>
    </div>
  );
}
