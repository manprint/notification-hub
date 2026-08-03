import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "../api/client";
import type { ApiError, ChannelType, DeliveryChannelOut, GroupChannelBindingOut, Severity } from "../api/types";
import ErrorBanner from "../components/ErrorBanner";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

interface ChannelBindingsProps {
  groupId: string;
  channels: DeliveryChannelOut[];
}

export default function ChannelBindings({ groupId, channels }: ChannelBindingsProps) {
  const queryClient = useQueryClient();
  const { data: bindings } = useQuery({
    queryKey: ["group-channel-bindings", groupId],
    queryFn: () => apiGet<GroupChannelBindingOut[]>(`/api/v1/groups/${groupId}/channels`),
  });
  const [error, setError] = useState<ApiError | null>(null);

  const byChannelId = new Map((bindings ?? []).map((b) => [b.channel_id, b]));

  async function bind(channelId: string, minSeverity: Severity) {
    setError(null);
    try {
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
    } catch (err) {
      setError(err as ApiError);
    }
  }

  async function unbind(channelId: string) {
    setError(null);
    try {
      await apiDelete(`/api/v1/groups/${groupId}/channels/${channelId}`);
      await queryClient.invalidateQueries({ queryKey: ["group-channel-bindings", groupId] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  function handleChange(channelId: string, value: string) {
    if (value === "") {
      void unbind(channelId);
    } else {
      void bind(channelId, value as Severity);
    }
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
                  <select
                    value={binding?.min_severity ?? ""}
                    onChange={(event) => handleChange(channel.id, event.target.value)}
                  >
                    <option value="">Non collegato</option>
                    {SEVERITIES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function channelTypeLabel(type: ChannelType): string {
  return { slack: "Slack", google_chat: "Google Chat" }[type];
}
