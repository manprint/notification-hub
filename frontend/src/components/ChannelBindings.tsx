import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "../api/client";
import type { ApiError, GroupChannelBindingOut, DeliveryChannelOut, Severity } from "../api/types";
import DataTable, { type DataTableColumn } from "./DataTable";
import ErrorBanner from "../components/ErrorBanner";
import SaveIndicator from "./SaveIndicator";
import { useAction } from "../hooks/useAction";
import { channelTypeLabel, severityLabel } from "../lib/format";

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
        } finally {
          // Anche se la scrittura fallisce: un 404 vuol dire che la lettura in
          // cache è vecchia, e senza il refetch ogni modifica successiva
          // ripartirebbe dalla stessa decisione sbagliata.
          await queryClient.invalidateQueries({ queryKey: ["group-channel-bindings", groupId] });
        }
      },
      {
        name: channelId,
        success: `«${channelName}»: inoltro da ${severityLabel(minSeverity)} in su.`,
      },
    );
  }

  async function unbind(channelId: string, channelName: string) {
    setLastSaved(channelId);
    await run(
      async () => {
        try {
          await apiDelete(`/api/v1/groups/${groupId}/channels/${channelId}`);
        } finally {
          await queryClient.invalidateQueries({ queryKey: ["group-channel-bindings", groupId] });
        }
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

  const columns: DataTableColumn<DeliveryChannelOut>[] = [
    {
      key: "channel",
      header: "Canale",
      render: (channel) => (
        <>
          {channel.name} ({channelTypeLabel(channel.type)})
        </>
      ),
    },
    {
      key: "severity",
      header: "Soglia minima",
      render: (channel) => {
        const binding = byChannelId.get(channel.id);
        const suspended = binding !== undefined && !binding.enabled;
        const value = binding ? (binding.enabled ? binding.min_severity : DISABLED_BINDING) : "";
        return (
          <div className="status-cell">
            <select
              aria-label={`Soglia di ${channel.name}`}
              value={value}
              disabled={busy !== null || !ready}
              onChange={(event) => handleChange(channel.id, event.target.value, channel.name)}
            >
              <option value="">Non collegato</option>
              {suspended && (
                <option value={DISABLED_BINDING} disabled>
                  Disattivato (soglia {severityLabel(binding.min_severity)})
                </option>
              )}
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {severityLabel(s)}
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
        );
      },
    },
  ];

  return (
    <>
      {loadError && <ErrorBanner error={loadError} />}
      {error && <ErrorBanner error={error} />}
      {/* Senza collegamenti letti la tabella non mostra righe: ogni canale
          sembrerebbe «Non collegato» e il primo cambio partirebbe da dati falsi. */}
      <DataTable
        caption="Soglie per canale"
        columns={columns}
        rows={bindings === undefined ? [] : channels}
        rowKey={(channel) => channel.id}
        loading={bindings === undefined && !loadError}
        error={loadError}
        emptyMessage="Nessun canale configurato."
      />
    </>
  );
}
