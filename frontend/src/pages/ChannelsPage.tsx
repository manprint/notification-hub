import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api/client";
import type {
  ApiError,
  ChannelType,
  DeliveryChannelOut,
  DeliveryChannelTestOut,
  GroupOut,
  OverrideMode,
  ReceiverChannelOverrideOut,
  Severity,
} from "../api/types";
import ChannelBindings from "../components/ChannelBindings";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorBanner from "../components/ErrorBanner";
import { useSession } from "../hooks/useSession";
import { ADMIN_ROLES, hasRole } from "../lib/roles";

const CHANNEL_TYPES: ChannelType[] = ["slack", "google_chat", "generic_webhook"];
const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

function CreateChannelForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState<ChannelType>("slack");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPost("/api/v1/channels", { name, type, webhook_url: webhookUrl });
      setName("");
      setWebhookUrl("");
      await queryClient.invalidateQueries({ queryKey: ["channels"] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <div className="card">
      <h3>Nuovo canale</h3>
      {error && <ErrorBanner error={error} />}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-row">
          <label htmlFor="channel-name">Nome</label>
          <input id="channel-name" required value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="channel-type">Tipo</label>
          <select id="channel-type" value={type} onChange={(event) => setType(event.target.value as ChannelType)}>
            {CHANNEL_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="channel-webhook">Webhook URL</label>
          <input
            id="channel-webhook"
            type="password"
            required
            value={webhookUrl}
            onChange={(event) => setWebhookUrl(event.target.value)}
          />
        </div>
        <button type="submit" className="primary">
          Crea canale
        </button>
      </form>
    </div>
  );
}

function EditChannelForm({ channel, onDone }: { channel: DeliveryChannelOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(channel.name);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [error, setError] = useState<ApiError | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await apiPatch(`/api/v1/channels/${channel.id}`, {
        name,
        webhook_url: webhookUrl || undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["channels"] });
      onDone();
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <div className="form-row">
        <label htmlFor={`channel-edit-name-${channel.id}`}>Nome</label>
        <input
          id={`channel-edit-name-${channel.id}`}
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor={`channel-edit-webhook-${channel.id}`}>Nuovo webhook URL</label>
        <input
          id={`channel-edit-webhook-${channel.id}`}
          type="password"
          placeholder="lascia vuoto per non cambiarlo"
          value={webhookUrl}
          onChange={(event) => setWebhookUrl(event.target.value)}
        />
      </div>
      <div className="toolbar">
        <button type="submit" className="primary">
          Salva
        </button>
        <button type="button" onClick={onDone}>
          Annulla
        </button>
      </div>
    </form>
  );
}

function DeleteChannelButton({ channel }: { channel: DeliveryChannelOut }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const queryClient = useQueryClient();

  async function confirmDelete() {
    try {
      await apiDelete(`/api/v1/channels/${channel.id}`);
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["channels"] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <div>
      {error && <ErrorBanner error={error} />}
      {open ? (
        <ConfirmDialog
          title={`Elimina canale "${channel.name}"`}
          expectedText={channel.name}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setOpen(false)}
        />
      ) : (
        <button onClick={() => setOpen(true)}>Elimina</button>
      )}
    </div>
  );
}

function ChannelRow({ channel, canManage }: { channel: DeliveryChannelOut; canManage: boolean }) {
  const [testResult, setTestResult] = useState<DeliveryChannelTestOut | null>(null);
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();

  async function runTest() {
    const result = await apiPost<DeliveryChannelTestOut>(`/api/v1/channels/${channel.id}/test`);
    setTestResult(result);
  }

  async function toggleEnabled() {
    await apiPatch(`/api/v1/channels/${channel.id}`, { enabled: !channel.enabled });
    await queryClient.invalidateQueries({ queryKey: ["channels"] });
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={6}>
          <EditChannelForm channel={channel} onDone={() => setEditing(false)} />
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>{channel.name}</td>
      <td>{channel.type}</td>
      <td>
        <code>{channel.webhook_hint}</code>
      </td>
      <td>{channel.enabled ? "attivo" : "disattivo"}</td>
      <td>
        {channel.last_success_at && <div>ultimo successo: {channel.last_success_at}</div>}
        {channel.last_error_at && <div>ultimo errore: {channel.last_error}</div>}
      </td>
      <td>
        {canManage && (
          <>
            <button onClick={() => void runTest()}>Invia messaggio di prova</button>
            <button onClick={() => void toggleEnabled()}>{channel.enabled ? "Disattiva" : "Attiva"}</button>
            <button onClick={() => setEditing(true)}>Modifica</button>
            <DeleteChannelButton channel={channel} />
          </>
        )}
        {testResult && (
          <div>{testResult.sent ? `Inviato (${testResult.detail})` : `Fallito: ${testResult.detail}`}</div>
        )}
      </td>
    </tr>
  );
}

function ReceiverOverridesPanel({
  receiverId,
  channels,
}: {
  receiverId: string;
  channels: DeliveryChannelOut[];
}) {
  const queryClient = useQueryClient();
  const { data: overrides, error } = useQuery<ReceiverChannelOverrideOut[], ApiError>({
    queryKey: ["receiver-overrides", receiverId],
    queryFn: () => apiGet<ReceiverChannelOverrideOut[]>(`/api/v1/receivers/${receiverId}/channels`),
  });

  async function remove(channelId: string) {
    await apiDelete(`/api/v1/receivers/${receiverId}/channels/${channelId}`);
    await queryClient.invalidateQueries({ queryKey: ["receiver-overrides", receiverId] });
  }

  const channelName = (channelId: string) => channels.find((c) => c.id === channelId)?.name ?? channelId;

  if (error) return <ErrorBanner error={error} />;
  if (!overrides || overrides.length === 0) {
    return <p style={{ color: "var(--color-text-muted)" }}>Nessun override per questo receiver.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Canale</th>
          <th>Modalità</th>
          <th>Soglia minima</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {overrides.map((o) => (
          <tr key={o.id}>
            <td>{channelName(o.channel_id)}</td>
            <td>{o.mode}</td>
            <td>{o.min_severity ?? "—"}</td>
            <td>
              <button onClick={() => void remove(o.channel_id)}>Rimuovi</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ReceiverOverrideForm({ channels }: { channels: DeliveryChannelOut[] }) {
  const [receiverId, setReceiverId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [mode, setMode] = useState<OverrideMode>("override");
  const [minSeverity, setMinSeverity] = useState<Severity>("error");
  const [error, setError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState(false);
  const queryClient = useQueryClient();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(false);
    try {
      await apiPost(`/api/v1/receivers/${receiverId}/channels`, {
        channel_id: channelId,
        mode,
        min_severity: mode === "override" ? minSeverity : undefined,
      });
      setSuccess(true);
      await queryClient.invalidateQueries({ queryKey: ["receiver-overrides", receiverId] });
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <div className="card">
      <h3>Override per receiver</h3>
      {error && <ErrorBanner error={error} />}
      {success && <p>Override salvato.</p>}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <div className="form-row">
          <label htmlFor="override-receiver">Receiver ID</label>
          <input
            id="override-receiver"
            required
            value={receiverId}
            onChange={(event) => setReceiverId(event.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="override-channel">Canale</label>
          <select
            id="override-channel"
            value={channelId}
            onChange={(event) => setChannelId(event.target.value)}
            required
          >
            <option value="" disabled>
              Scegli un canale
            </option>
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="override-mode">Modalità</label>
          <select
            id="override-mode"
            value={mode}
            onChange={(event) => setMode(event.target.value as OverrideMode)}
          >
            <option value="override">override</option>
            <option value="mute">mute</option>
          </select>
        </div>
        {mode === "override" && (
          <div className="form-row">
            <label htmlFor="override-severity">Soglia minima</label>
            <select
              id="override-severity"
              value={minSeverity}
              onChange={(event) => setMinSeverity(event.target.value as Severity)}
            >
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        )}
        <button type="submit" className="primary">
          Salva override
        </button>
      </form>

      {receiverId && (
        <>
          <h4>Override attivi per questo receiver</h4>
          <ReceiverOverridesPanel receiverId={receiverId} channels={channels} />
        </>
      )}
    </div>
  );
}

export default function ChannelsPage() {
  const { role } = useSession();
  const canManage = hasRole(role, ADMIN_ROLES);
  const { data: channels, error } = useQuery<DeliveryChannelOut[], ApiError>({
    queryKey: ["channels"],
    queryFn: () => apiGet<DeliveryChannelOut[]>("/api/v1/channels"),
  });
  const { data: groups } = useQuery({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });
  const [selectedGroupId, setSelectedGroupId] = useState<string>("");

  return (
    <div>
      <h1>Canali</h1>
      {error && <ErrorBanner error={error} />}

      {canManage && <CreateChannelForm />}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Nome</th>
              <th>Tipo</th>
              <th>Webhook</th>
              <th>Stato</th>
              <th>Diagnostica</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {channels?.map((c) => <ChannelRow key={c.id} channel={c} canManage={canManage} />)}
          </tbody>
        </table>
      </div>

      {canManage && channels && (
        <div className="card">
          <h3>Soglie per gruppo</h3>
          <select value={selectedGroupId} onChange={(event) => setSelectedGroupId(event.target.value)}>
            <option value="">Scegli un gruppo</option>
            {groups?.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
          {selectedGroupId && <ChannelBindings groupId={selectedGroupId} channels={channels} />}
        </div>
      )}

      {canManage && channels && <ReceiverOverrideForm channels={channels} />}
    </div>
  );
}
