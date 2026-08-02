import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPatch, apiPost } from "../api/client";
import type {
  ApiError,
  ChannelType,
  DeliveryChannelOut,
  DeliveryChannelTestOut,
  GroupOut,
  OverrideMode,
  Severity,
} from "../api/types";
import ChannelBindings from "../components/ChannelBindings";
import ErrorBanner from "../components/ErrorBanner";

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

function ChannelRow({ channel }: { channel: DeliveryChannelOut }) {
  const [testResult, setTestResult] = useState<DeliveryChannelTestOut | null>(null);
  const queryClient = useQueryClient();

  async function runTest() {
    const result = await apiPost<DeliveryChannelTestOut>(`/api/v1/channels/${channel.id}/test`);
    setTestResult(result);
  }

  async function toggleEnabled() {
    await apiPatch(`/api/v1/channels/${channel.id}`, { enabled: !channel.enabled });
    await queryClient.invalidateQueries({ queryKey: ["channels"] });
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
        <button onClick={() => void runTest()}>Invia messaggio di prova</button>
        <button onClick={() => void toggleEnabled()}>{channel.enabled ? "Disattiva" : "Attiva"}</button>
        {testResult && (
          <div>{testResult.sent ? `Inviato (${testResult.detail})` : `Fallito: ${testResult.detail}`}</div>
        )}
      </td>
    </tr>
  );
}

function ReceiverOverrideForm({ channels }: { channels: DeliveryChannelOut[] }) {
  const [receiverId, setReceiverId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [mode, setMode] = useState<OverrideMode>("override");
  const [minSeverity, setMinSeverity] = useState<Severity>("error");
  const [error, setError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState(false);

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
    </div>
  );
}

export default function ChannelsPage() {
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

      <CreateChannelForm />

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
          <tbody>{channels?.map((c) => <ChannelRow key={c.id} channel={c} />)}</tbody>
        </table>
      </div>

      {channels && (
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

      {channels && <ReceiverOverrideForm channels={channels} />}
    </div>
  );
}
