import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPatch } from "../api/client";
import type { ApiError, TenantOut } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";

interface ConflictingReceiver {
  name: string;
  max_body_bytes: number;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: tenant, isLoading } = useQuery({
    queryKey: ["tenant"],
    queryFn: () => apiGet<TenantOut>("/api/v1/tenant"),
  });

  const [maxBodyBytes, setMaxBodyBytes] = useState<string>("");
  const [retentionDays, setRetentionDays] = useState<string>("");
  const [maxNotificationsPerDay, setMaxNotificationsPerDay] = useState<string>("");
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

  return (
    <div>
      <h1>Impostazioni</h1>
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
        <button type="submit" className="primary">
          Salva
        </button>
      </form>
    </div>
  );
}
