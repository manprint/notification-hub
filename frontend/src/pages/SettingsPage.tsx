import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPatch } from "../api/client";
import type { ApiError, TenantOut } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";
import SettingsTabs from "../components/SettingsTabs";
import { useSession } from "../hooks/useSession";

interface ConflictingReceiver {
  name: string;
  max_body_bytes: number;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { role } = useSession();
  const { data: tenant, isLoading } = useQuery({
    queryKey: ["tenant"],
    queryFn: () => apiGet<TenantOut>("/api/v1/tenant"),
  });

  const [maxBodyBytes, setMaxBodyBytes] = useState<string>("");
  const [retentionDays, setRetentionDays] = useState<string>("");
  const [maxNotificationsPerDay, setMaxNotificationsPerDay] = useState<string>("");
  const [auditRetentionDays, setAuditRetentionDays] = useState<string>("");
  const [error, setError] = useState<ApiError | null>(null);
  const [conflicting, setConflicting] = useState<ConflictingReceiver[] | null>(null);

  if (isLoading) return <p>Caricamento…</p>;
  if (!tenant) return null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setConflicting(null);
    try {
      await apiPatch("/api/v1/tenant", {
        max_body_bytes: maxBodyBytes ? Number(maxBodyBytes) : undefined,
        retention_days: retentionDays ? Number(retentionDays) : undefined,
        max_notifications_per_day: maxNotificationsPerDay ? Number(maxNotificationsPerDay) : undefined,
        audit_retention_days: auditRetentionDays ? Number(auditRetentionDays) : undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["tenant"] });
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError);
      const receivers = apiError.extra.conflicting_receivers;
      if (Array.isArray(receivers)) {
        setConflicting(receivers as ConflictingReceiver[]);
      }
    }
  }

  // Le quote del tenant restano una decisione dell'owner: un admin arriva qui
  // per l'audit, e vede le schede ma non il modulo (backend: require_owner su
  // PATCH /api/v1/tenant).
  // `role === null` significa sessione non ancora risolta, non "ruolo
  // insufficiente": nasconderle il modulo la farebbe sparire per un istante a
  // ogni caricamento. Il rifiuto vero lo dà comunque il backend.
  if (role !== null && role !== "owner") {
    return (
      <div>
        <h1>Impostazioni</h1>
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
      <h1>Impostazioni</h1>
      <SettingsTabs />
      {error && <ErrorBanner error={error} />}
      {conflicting && (
        <div className="error-banner">
          <p>Questi receiver hanno un limite superiore a quello richiesto:</p>
          <ul>
            {conflicting.map((r) => (
              <li key={r.name}>
                {r.name}: {r.max_body_bytes} byte
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card">
        <p>Tenant: {tenant.name}</p>
        <p>Cap corpo attuale: {tenant.max_body_bytes} byte</p>
        <p>Retention attuale: {tenant.retention_days ?? "illimitata"} giorni</p>
        <p>Quota giornaliera attuale: {tenant.max_notifications_per_day ?? "illimitata"}</p>
        <p>Retention audit attuale: {tenant.audit_retention_days ?? "illimitata"} giorni</p>
      </div>

      <form onSubmit={(event) => void handleSubmit(event)} className="card">
        <div className="form-row">
          <label htmlFor="max-body-bytes">Cap corpo (byte)</label>
          <input
            id="max-body-bytes"
            type="number"
            placeholder={String(tenant.max_body_bytes)}
            value={maxBodyBytes}
            onChange={(event) => setMaxBodyBytes(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="retention-days">Retention (giorni)</label>
          <input
            id="retention-days"
            type="number"
            placeholder={String(tenant.retention_days ?? "")}
            value={retentionDays}
            onChange={(event) => setRetentionDays(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="max-notifications">Quota giornaliera notifiche</label>
          <input
            id="max-notifications"
            type="number"
            placeholder={String(tenant.max_notifications_per_day ?? "")}
            value={maxNotificationsPerDay}
            onChange={(event) => setMaxNotificationsPerDay(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="audit-retention-days">Retention audit (giorni)</label>
          <input
            id="audit-retention-days"
            type="number"
            placeholder={String(tenant.audit_retention_days ?? "")}
            value={auditRetentionDays}
            onChange={(event) => setAuditRetentionDays(event.target.value)}
          />
          <p className="field-hint">
            Separata dalla retention delle notifiche: l'audit deve poter raccontare chi ha gestito
            una notifica anche dopo che la notifica è stata cancellata.
          </p>
        </div>
        <button type="submit" className="primary">
          Salva
        </button>
      </form>
    </div>
  );
}
