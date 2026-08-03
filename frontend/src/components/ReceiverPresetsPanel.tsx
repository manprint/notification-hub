import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPut } from "../api/client";
import type { ApiError, ReceiverPresetOut, SeverityPresetOut } from "../api/types";
import ErrorBanner from "./ErrorBanner";
import { useSession } from "../hooks/useSession";
import { MEMBER_ROLES, hasRole } from "../lib/roles";

/** Preset applicati a un receiver: quali, e in che ordine vengono valutati.
 *
 *  Ogni modifica invia l'elenco completo (PUT): attaccare, staccare e riordinare
 *  sono la stessa operazione, quindi non esistono stati intermedi in cui il
 *  receiver ha posizioni doppie o buchi. */
export default function ReceiverPresetsPanel({ receiverId }: { receiverId: string }) {
  const { role } = useSession();
  const canManage = hasRole(role, MEMBER_ROLES);
  const queryClient = useQueryClient();
  const [error, setError] = useState<ApiError | null>(null);

  const { data: applied, error: appliedError } = useQuery<ReceiverPresetOut[], ApiError>({
    queryKey: ["receiver-presets", receiverId],
    queryFn: () => apiGet<ReceiverPresetOut[]>(`/api/v1/receivers/${receiverId}/presets`),
  });

  const { data: all } = useQuery<SeverityPresetOut[], ApiError>({
    queryKey: ["presets"],
    queryFn: () => apiGet<SeverityPresetOut[]>("/api/v1/severity-presets"),
  });

  const appliedList = applied ?? [];
  const appliedIds = appliedList.map((p) => p.preset_id);
  const available = (all ?? []).filter((p) => !appliedIds.includes(p.id));

  async function save(presetIds: string[]) {
    setError(null);
    try {
      await apiPut(`/api/v1/receivers/${receiverId}/presets`, { preset_ids: presetIds });
      await queryClient.invalidateQueries({ queryKey: ["receiver-presets", receiverId] });
      await queryClient.invalidateQueries({ queryKey: ["severity-chain", receiverId] });
      await queryClient.invalidateQueries({ queryKey: ["severity-replay", receiverId] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  function move(index: number, delta: number) {
    const next = [...appliedIds];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    void save(next);
  }

  return (
    <div className="card">
      <h3>Preset di regole applicati</h3>
      <p className="card-hint">
        Un preset porta con sé le sue regole, valutate <strong>dopo</strong> quelle scritte su
        questo receiver e nell'ordine in cui compaiono qui. I preset si creano e si modificano
        nella sezione <Link to="/presets">Preset di regole</Link>.
      </p>
      <p className="card-hint">
        Metti i preset specifici (tar, rclone, PostgreSQL…) <strong>prima</strong> di «Bash
        generico»: quest'ultimo contiene una regola di riserva molto larga che vincerebbe su
        tutto quello che viene dopo.
      </p>
      {appliedError && <ErrorBanner error={appliedError} />}
      {error && <ErrorBanner error={error} />}

      {appliedList.length === 0 ? (
        <p className="card-hint">Nessun preset applicato: valgono solo le regole qui sotto.</p>
      ) : (
        <ol className="chain-list" aria-label="Preset applicati">
          {appliedList.map((preset, index) => (
            <li key={preset.preset_id}>
              <strong>{preset.name}</strong> — {preset.rules_count} regole
              {preset.description && <div className="cell-diagnostics">{preset.description}</div>}
              {canManage && (
                <div className="row-actions">
                  <button
                    aria-label={`Sposta su ${preset.name}`}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                  >
                    ↑
                  </button>
                  <button
                    aria-label={`Sposta giù ${preset.name}`}
                    disabled={index === appliedList.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    ↓
                  </button>
                  <button
                    onClick={() =>
                      void save(appliedIds.filter((id) => id !== preset.preset_id))
                    }
                  >
                    Togli
                  </button>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}

      {canManage && available.length > 0 && (
        <>
          <h4>Preset disponibili</h4>
          <ul className="check-list" aria-label="Preset disponibili">
            {available.map((preset) => (
              <li key={preset.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={false}
                    aria-label={`Applica ${preset.name}`}
                    onChange={() => void save([...appliedIds, preset.id])}
                  />
                  <span>
                    <strong>{preset.name}</strong> — {preset.rules_count} regole
                    {preset.description && (
                      <div className="cell-diagnostics">{preset.description}</div>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
