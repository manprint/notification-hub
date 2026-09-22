import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "../api/client";
import type { ApiError, GroupChannelBindingOut, DeliveryChannelOut, Severity } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";
import SaveIndicator from "./SaveIndicator";
import { useAction } from "../hooks/useAction";
import { channelTypeLabel } from "../lib/format";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

/** Valore della tendina per un collegamento che esiste ma e' disattivato: non
 *  e' "Non collegato" (sceglierlo lo cancellerebbe) e non e' una soglia attiva. */
const DISABLED_BINDING = "__disattivato__";

/** Quanto resta visibile "Non salvato" accanto alla riga. Il dettaglio resta nel
 *  banner sopra la tabella; il segno sulla riga torna neutro da solo, come fa
 *  "Salvato", invece di restare li' finche' non si tocca un'altra tendina. */
const FAILED_VISIBLE_MS = 4000;

interface ChannelBindingsProps {
  groupId: string;
  channels: DeliveryChannelOut[];
}

/** Soglie di inoltro di UN gruppo. Chi lo usa deve montarlo con
 *  `key={groupId}`: cambiando gruppo, lo stato della riga appena salvata e
 *  l'errore dell'ultima azione appartengono al gruppo di prima. */
export default function ChannelBindings({ groupId, channels }: ChannelBindingsProps) {
  const queryClient = useQueryClient();
  const {
    data: bindings,
    error: loadError,
    isLoading,
  } = useQuery<GroupChannelBindingOut[], ApiError>({
    queryKey: ["group-channel-bindings", groupId],
    queryFn: () => apiGet<GroupChannelBindingOut[]>(`/api/v1/groups/${groupId}/channels`),
  });
  const { busy, error, saveState, run } = useAction();
  // Il riscontro sta sulla riga che è cambiata: la tendina salva da sola, e
  // senza un segno accanto non si distingue da una che non ha fatto niente.
  const [lastSaved, setLastSaved] = useState<string | null>(null);

  useEffect(() => {
    if (saveState !== "failed" || lastSaved === null) return;
    const timer = window.setTimeout(() => setLastSaved(null), FAILED_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [saveState, lastSaved]);

  const byChannelId = new Map((bindings ?? []).map((b) => [b.channel_id, b]));
  // Senza i collegamenti letti davvero ogni riga sembrerebbe «Non collegato»:
  // cambiare una soglia partirebbe da uno stato falso (POST su un collegamento
  // che esiste gia').
  const ready = bindings !== undefined && !loadError;

  async function bind(channelId: string, minSeverity: Severity, channelName: string) {
    setLastSaved(channelId);
    await run(
      async () => {
        const existing = byChannelId.get(channelId);
        if (existing) {
          await apiPut(`/api/v1/groups/${groupId}/channels/${channelId}`, {
            min_severity: minSeverity,
            enabled: true,
          });
        } else {
          await apiPost(`/api/v1/groups/${groupId}/channels`, {
            channel_id: channelId,
            min_severity: minSeverity,
          });
        }
        await queryClient.invalidateQueries({ queryKey: ["group-channel-bindings", groupId] });
      },
      { name: channelId, success: `«${channelName}»: inoltro da ${minSeverity} in su.` },
    );
  }

  async function unbind(channelId: string, channelName: string) {
    setLastSaved(channelId);
    await run(
      async () => {
        await apiDelete(`/api/v1/groups/${groupId}/channels/${channelId}`);
        await queryClient.invalidateQueries({ queryKey: ["group-channel-bindings", groupId] });
      },
      { name: channelId, success: `«${channelName}» scollegato dal gruppo.` },
    );
  }

  function handleChange(channelId: string, value: string, channelName: string) {
    if (value === DISABLED_BINDING) return;
    if (value === "") {
      void unbind(channelId, channelName);
    } else {
      void bind(channelId, value as Severity, channelName);
    }
  }

  function stateOf(channelId: string) {
    if (busy === channelId) return "saving" as const;
    if (lastSaved === channelId) return saveState;
    return "idle" as const;
  }

  return (
    <div className="table-wrap">
      {loadError && <ErrorBanner error={loadError} />}
      {error && <ErrorBanner error={error} />}
      {isLoading && <p className="card-hint">Caricamento dei collegamenti…</p>}
      {bindings !== undefined && (
        <table>
          <thead>
            <tr>
              <th>Canale</th>
              <th>Soglia minima</th>
            </tr>
          </thead>
          <tbody>
            {channels.map((channel) => {
              const binding = byChannelId.get(channel.id);
              const suspended = binding !== undefined && !binding.enabled;
              const value = binding ? (binding.enabled ? binding.min_severity : DISABLED_BINDING) : "";
              return (
                <tr key={channel.id}>
                  <td>
                    {channel.name} ({channelTypeLabel(channel.type)})
                  </td>
                  <td>
                    <div className="status-cell">
                      <select
                        aria-label={`Soglia di ${channel.name}`}
                        value={value}
                        disabled={busy !== null || !ready}
                        onChange={(event) =>
                          handleChange(channel.id, event.target.value, channel.name)
                        }
                      >
                        <option value="">Non collegato</option>
                        {suspended && (
                          <option value={DISABLED_BINDING} disabled>
                            Disattivato (soglia {binding.min_severity})
                          </option>
                        )}
                        {SEVERITIES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                      {suspended && (
                        <span
                          className="status-pill warn"
                          title="Il collegamento esiste ma è disattivato: nessun inoltro. Scegli una soglia per riattivarlo."
                        >
                          disattivato: nessun inoltro
                        </span>
                      )}
                      <SaveIndicator state={stateOf(channel.id)} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
