import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "../api/client";
import type { ApiError, GroupChannelBindingOut, DeliveryChannelOut, Severity } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";
import SaveIndicator from "./SaveIndicator";
import { useAction } from "../hooks/useAction";
import { channelTypeLabel } from "../lib/format";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

interface ChannelBindingsProps {
  groupId: string;
  channels: DeliveryChannelOut[];
}

export default function ChannelBindings({ groupId, channels }: ChannelBindingsProps) {
  const queryClient = useQueryClient();
  const { data: bindings } = useQuery<GroupChannelBindingOut[], ApiError>({
    queryKey: ["group-channel-bindings", groupId],
    queryFn: () => apiGet<GroupChannelBindingOut[]>(`/api/v1/groups/${groupId}/channels`),
  });
  const { busy, error, saveState, run } = useAction();
  // Il riscontro sta sulla riga che è cambiata: la tendina salva da sola, e
  // senza un segno accanto non si distingue da una che non ha fatto niente.
  const [lastSaved, setLastSaved] = useState<string | null>(null);

  const byChannelId = new Map((bindings ?? []).map((b) => [b.channel_id, b]));

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
      {error && <ErrorBanner error={error} />}
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
            return (
              <tr key={channel.id}>
                <td>
                  {channel.name} ({channelTypeLabel(channel.type)})
                </td>
                <td>
                  <div className="status-cell">
                    <select
                      aria-label={`Soglia di ${channel.name}`}
                      value={binding?.min_severity ?? ""}
                      disabled={busy !== null}
                      onChange={(event) =>
                        handleChange(channel.id, event.target.value, channel.name)
                      }
                    >
                      <option value="">Non collegato</option>
                      {SEVERITIES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                    <SaveIndicator state={stateOf(channel.id)} />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
