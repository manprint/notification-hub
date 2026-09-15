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

interface ConflictingReceiver {
  name: string;
  max_body_bytes: number;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { role } = useSession();
  const { data: tenant, isLoading } = useQuery<TenantOut, ApiError>({
    queryKey: ["tenant"],
    queryFn: () => apiGet<TenantOut>("/api/v1/tenant"),
  });

  const [maxBodyBytes, setMaxBodyBytes] = useState<string>("");
  const [retentionDays, setRetentionDays] = useState<string>("");
  const [maxNotificationsPerDay, setMaxNotificationsPerDay] = useState<string>("");
  const [auditRetentionDays, setAuditRetentionDays] = useState<string>("");
  const [conflicting, setConflicting] = useState<ConflictingReceiver[] | null>(null);
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setConflicting(null);
    const ok = await run(
      async () => {
        try {
          await apiPatch("/api/v1/tenant", {
            max_body_bytes: maxBodyBytes ? Number(maxBodyBytes) : undefined,
            retention_days: retentionDays ? Number(retentionDays) : undefined,
            max_notifications_per_day: maxNotificationsPerDay
              ? Number(maxNotificationsPerDay)
              : undefined,
            audit_retention_days: auditRetentionDays ? Number(auditRetentionDays) : undefined,
          });
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
    // A salvataggio riuscito i campi tornano vuoti: ora il valore in vigore è
    // quello mostrato sopra, e lasciare il numero digitato farebbe credere che
    // ci sia ancora una modifica in sospeso.
    if (ok) {
      setMaxBodyBytes("");
      setRetentionDays("");
      setMaxNotificationsPerDay("");
      setAuditRetentionDays("");
    }
  }

  if (isLoading) return <EmptyState message="Caricamento…" />;
  if (!tenant) return null;

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
          <ul>
            {conflicting.map((r) => (
              <li key={r.name}>
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
          <div>
            <span className="detail-label">Retention notifiche</span>
            <p className="detail-value">
              {tenant.retention_days === null ? "illimitata" : `${tenant.retention_days} giorni`}
            </p>
          </div>
          <div>
            <span className="detail-label">Quota giornaliera</span>
            <p className="detail-value">
              {tenant.max_notifications_per_day === null
                ? "illimitata"
                : `${tenant.max_notifications_per_day} notifiche`}
            </p>
          </div>
          <div>
            <span className="detail-label">Retention audit</span>
            <p className="detail-value">
              {tenant.audit_retention_days === null
                ? "illimitata"
                : `${tenant.audit_retention_days} giorni`}
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={(event) => void handleSubmit(event)} className="card">
        <div className="card-header">
          <h3>Modifica le quote</h3>
        </div>
        <p className="card-hint">
          Un campo lasciato vuoto non cambia il valore in vigore: si compila solo ciò che si vuole
          modificare.
        </p>
        <div className="form-grid">
          <Field
            id="max-body-bytes"
            label="Cap corpo (byte)"
            optional
            hint={`In vigore: ${formatBytes(tenant.max_body_bytes)}. Nessun receiver può superarlo.`}
          >
            <input
              {...fieldAria("max-body-bytes", { hint: true })}
              type="number"
              min={1}
              placeholder={String(tenant.max_body_bytes)}
              value={maxBodyBytes}
              onChange={(event) => setMaxBodyBytes(event.target.value)}
            />
          </Field>
          <Field
            id="retention-days"
            label="Retention (giorni)"
            optional
            hint="Dopo quanti giorni le notifiche vengono cancellate dal job notturno."
          >
            <input
              {...fieldAria("retention-days", { hint: true })}
              type="number"
              min={1}
              placeholder={String(tenant.retention_days ?? "illimitata")}
              value={retentionDays}
              onChange={(event) => setRetentionDays(event.target.value)}
            />
          </Field>
          <Field
            id="max-notifications"
            label="Quota giornaliera notifiche"
            optional
            hint="Superata la quota, l'ingestion risponde 429 fino al giorno dopo."
          >
            <input
              {...fieldAria("max-notifications", { hint: true })}
              type="number"
              min={1}
              placeholder={String(tenant.max_notifications_per_day ?? "illimitata")}
              value={maxNotificationsPerDay}
              onChange={(event) => setMaxNotificationsPerDay(event.target.value)}
            />
          </Field>
          <Field
            id="audit-retention-days"
            label="Retention audit (giorni)"
            optional
            hint="Separata dalla retention delle notifiche: l'audit deve poter raccontare chi ha gestito una notifica anche dopo che la notifica è stata cancellata."
          >
            <input
              {...fieldAria("audit-retention-days", { hint: true })}
              type="number"
              min={1}
              placeholder={String(tenant.audit_retention_days ?? "illimitata")}
              value={auditRetentionDays}
              onChange={(event) => setAuditRetentionDays(event.target.value)}
            />
          </Field>
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
