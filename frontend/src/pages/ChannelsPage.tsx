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
  ReceiverOut,
  Severity,
} from "../api/types";
import ChannelBindings from "../components/ChannelBindings";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import Modal from "../components/Modal";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { channelTypeLabel, formatDateTime } from "../lib/format";
import { ADMIN_ROLES, hasRole } from "../lib/roles";

const CHANNEL_TYPES: ChannelType[] = ["slack", "google_chat"];
const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];

/** Il webhook è una credenziale: se non è un URL https il salvataggio fallisce
 *  comunque, ma dirlo qui evita di scoprire un errore di copia-incolla dopo un
 *  giro di rete. */
function validateWebhook(url: string): string | null {
  if (url.trim() === "") return "Il webhook URL è obbligatorio.";
  if (!/^https:\/\/\S+$/.test(url.trim())) return "Deve essere un URL https:// completo.";
  return null;
}

function CreateChannelForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState<ChannelType>("slack");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; webhook?: string }>({});
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const errors: { name?: string; webhook?: string } = {};
    if (name.trim() === "") errors.name = "Il nome del canale è obbligatorio.";
    const webhookError = validateWebhook(webhookUrl);
    if (webhookError) errors.webhook = webhookError;
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const ok = await run(
      async () => {
        await apiPost("/api/v1/channels", {
          name: name.trim(),
          type,
          webhook_url: webhookUrl.trim(),
        });
        await queryClient.invalidateQueries({ queryKey: ["channels"] });
      },
      { success: `Canale "${name.trim()}" creato.` },
    );
    if (ok) {
      setName("");
      setWebhookUrl("");
    }
  }

  return (
    <details className="card collapsible">
      <summary>Nuovo canale</summary>
      <p className="card-hint">
        Un canale è la destinazione degli inoltri: il webhook di uno spazio Slack o Google Chat.
        L'URL viene cifrato e non viene più mostrato per intero.
      </p>
      {error && <ErrorBanner error={error} />}
      <form className="form-stacked" onSubmit={(event) => void handleSubmit(event)}>
        <RequiredLegend />
        <Field id="channel-name" label="Nome" required error={fieldErrors.name}>
          <input
            {...fieldAria("channel-name", { error: fieldErrors.name })}
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="channel-type" label="Tipo">
          <select
            id="channel-type"
            value={type}
            onChange={(event) => setType(event.target.value as ChannelType)}
          >
            {CHANNEL_TYPES.map((t) => (
              <option key={t} value={t}>
                {channelTypeLabel(t)}
              </option>
            ))}
          </select>
        </Field>
        <Field
          id="channel-webhook"
          label="Webhook URL"
          required
          error={fieldErrors.webhook}
          hint="Slack: https://hooks.slack.com/services/… · Google Chat: https://chat.googleapis.com/v1/spaces/…"
        >
          <input
            {...fieldAria("channel-webhook", { hint: true, error: fieldErrors.webhook })}
            type="password"
            required
            placeholder="https://hooks.slack.com/services/…"
            value={webhookUrl}
            onChange={(event) => setWebhookUrl(event.target.value)}
          />
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Creazione…" : "Crea canale"}
          </button>
        </div>
      </form>
    </details>
  );
}

function EditChannelForm({ channel, onDone }: { channel: DeliveryChannelOut; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(channel.name);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; webhook?: string }>({});
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const errors: { name?: string; webhook?: string } = {};
    if (name.trim() === "") errors.name = "Il nome del canale è obbligatorio.";
    // Campo vuoto significa "non cambiare il webhook": si valida solo se c'è.
    if (webhookUrl.trim() !== "") {
      const webhookError = validateWebhook(webhookUrl);
      if (webhookError) errors.webhook = webhookError;
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    const ok = await run(
      async () => {
        await apiPatch(`/api/v1/channels/${channel.id}`, {
          name: name.trim(),
          webhook_url: webhookUrl.trim() || undefined,
        });
        await queryClient.invalidateQueries({ queryKey: ["channels"] });
      },
      { success: "Canale aggiornato." },
    );
    if (ok) onDone();
  }

  const nameId = `channel-edit-name-${channel.id}`;
  const webhookId = `channel-edit-webhook-${channel.id}`;

  return (
    <form onSubmit={(event) => void handleSubmit(event)}>
      {error && <ErrorBanner error={error} />}
      <RequiredLegend />
      <Field id={nameId} label="Nome" required error={fieldErrors.name}>
        <input
          {...fieldAria(nameId, { error: fieldErrors.name })}
          required
          maxLength={120}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </Field>
      <Field
        id={webhookId}
        label="Nuovo webhook URL"
        optional
        error={fieldErrors.webhook}
        hint="Lascia vuoto per tenere quello attuale."
      >
        <input
          {...fieldAria(webhookId, { hint: true, error: fieldErrors.webhook })}
          type="password"
          placeholder="lascia vuoto per non cambiarlo"
          value={webhookUrl}
          onChange={(event) => setWebhookUrl(event.target.value)}
        />
      </Field>
      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy !== null}>
          {busy !== null ? "Salvataggio…" : "Salva"}
        </button>
        <button type="button" onClick={onDone}>
          Annulla
        </button>
      </div>
    </form>
  );
}

function ChannelRow({ channel, canManage }: { channel: DeliveryChannelOut; canManage: boolean }) {
  const [testResult, setTestResult] = useState<DeliveryChannelTestOut | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const queryClient = useQueryClient();
  const { busy, error: actionError, run } = useAction();

  async function runTest() {
    await run(
      async () => {
        const result = await apiPost<DeliveryChannelTestOut>(
          `/api/v1/channels/${channel.id}/test`,
        );
        setTestResult(result);
        // Il webhook ha risposto male: l'API ha detto 200 ma la prova è
        // fallita, e per chi guarda è comunque un errore da segnalare.
        if (!result.sent) {
          const failure: ApiError = {
            status: 0,
            type: "/problems/channel-test-failed",
            title: "Prova fallita",
            detail: result.detail,
            extra: {},
          };
          throw failure;
        }
      },
      { name: "test", success: "Messaggio di prova inviato." },
    );
  }

  async function toggleEnabled() {
    await run(
      async () => {
        await apiPatch(`/api/v1/channels/${channel.id}`, { enabled: !channel.enabled });
        await queryClient.invalidateQueries({ queryKey: ["channels"] });
      },
      {
        name: "toggle",
        success: channel.enabled
          ? `Canale "${channel.name}" disattivato.`
          : `Canale "${channel.name}" attivato.`,
      },
    );
  }

  async function confirmDelete() {
    setConfirmingDelete(false);
    await run(
      async () => {
        await apiDelete(`/api/v1/channels/${channel.id}`);
        await queryClient.invalidateQueries({ queryKey: ["channels"] });
      },
      { name: "delete", success: `Canale "${channel.name}" eliminato.` },
    );
  }

  return (
    <tr>
      <td>{channel.name}</td>
      <td>{channelTypeLabel(channel.type)}</td>
      <td>
        <code>{channel.webhook_hint}</code>
      </td>
      <td>
        <span className={channel.enabled ? "status-pill ok" : "status-pill warn"}>
          {channel.enabled ? "attivo" : "disattivo"}
        </span>
      </td>
      <td className="cell-diagnostics">
        {channel.last_success_at && <div>ultimo successo: {formatDateTime(channel.last_success_at)}</div>}
        {channel.last_error_at && (
          <div>
            ultimo errore ({formatDateTime(channel.last_error_at)}): {channel.last_error}
          </div>
        )}
        {!channel.last_success_at && !channel.last_error_at && <span>nessun invio registrato</span>}
        {testResult && (
          <div>{testResult.sent ? `Prova inviata (${testResult.detail})` : `Prova fallita: ${testResult.detail}`}</div>
        )}
      </td>
      <td>
        {canManage && (
          <div className="row-actions">
            <button disabled={busy !== null} onClick={() => void runTest()}>
              {busy === "test" ? "Attendi…" : "Prova"}
            </button>
            <button disabled={busy !== null} onClick={() => void toggleEnabled()}>
              {channel.enabled ? "Disattiva" : "Attiva"}
            </button>
            <button disabled={busy !== null} onClick={() => setEditing(true)}>
              Modifica
            </button>
            <button className="danger" disabled={busy !== null} onClick={() => setConfirmingDelete(true)}>
              Elimina
            </button>
          </div>
        )}
        {actionError && <ErrorBanner error={actionError} />}
        {editing && (
          <Modal title={`Modifica "${channel.name}"`} onClose={() => setEditing(false)}>
            <EditChannelForm channel={channel} onDone={() => setEditing(false)} />
          </Modal>
        )}
        {confirmingDelete && (
          <ConfirmDialog
            title={`Elimina canale "${channel.name}"`}
            expectedText={channel.name}
            confirmLabel="Elimina canale"
            onConfirm={() => void confirmDelete()}
            onCancel={() => setConfirmingDelete(false)}
          >
            <p>Verranno rimossi anche i collegamenti ai gruppi, gli override e lo storico consegne.</p>
          </ConfirmDialog>
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
  const { busy, error: actionError, run } = useAction();
  const { data: overrides, error } = useQuery<ReceiverChannelOverrideOut[], ApiError>({
    queryKey: ["receiver-overrides", receiverId],
    queryFn: () => apiGet<ReceiverChannelOverrideOut[]>(`/api/v1/receivers/${receiverId}/channels`),
  });

  async function remove(channelId: string) {
    await run(
      async () => {
        await apiDelete(`/api/v1/receivers/${receiverId}/channels/${channelId}`);
        await queryClient.invalidateQueries({ queryKey: ["receiver-overrides", receiverId] });
      },
      { name: channelId, success: "Override rimosso." },
    );
  }

  const channelName = (channelId: string) =>
    channels.find((c) => c.id === channelId)?.name ?? channelId;

  if (error) return <ErrorBanner error={error} />;
  if (!overrides || overrides.length === 0) {
    return <p className="card-hint">Nessun override per questo receiver: valgono le soglie di gruppo.</p>;
  }

  return (
    <div className="table-wrap">
      {actionError && <ErrorBanner error={actionError} />}
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
              <td>{o.mode === "mute" ? "silenziato" : "soglia sostituita"}</td>
              <td>{o.min_severity ?? "—"}</td>
              <td>
                <div className="row-actions">
                  <button
                    className="danger"
                    disabled={busy !== null}
                    onClick={() => void remove(o.channel_id)}
                  >
                    {busy === o.channel_id ? "Rimozione…" : "Rimuovi"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReceiverOverrideForm({ channels }: { channels: DeliveryChannelOut[] }) {
  const [receiverId, setReceiverId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [mode, setMode] = useState<OverrideMode>("override");
  const [minSeverity, setMinSeverity] = useState<Severity>("error");
  const queryClient = useQueryClient();
  const { busy, error, run } = useAction();

  // Il receiver si sceglie da un elenco: prima era un campo di testo libero in
  // cui incollare un UUID a mano, e qualunque valore non-UUID faceva rispondere
  // 500 all'API.
  const { data: receivers } = useQuery<ReceiverOut[], ApiError>({
    queryKey: ["receivers-all"],
    queryFn: () => apiGet<ReceiverOut[]>("/api/v1/receivers"),
  });

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    await run(
      async () => {
        await apiPost(`/api/v1/receivers/${receiverId}/channels`, {
          channel_id: channelId,
          mode,
          min_severity: mode === "override" ? minSeverity : undefined,
        });
        await queryClient.invalidateQueries({ queryKey: ["receiver-overrides", receiverId] });
      },
      { success: "Override salvato." },
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3>Override per receiver</h3>
      </div>
      <p className="card-hint">
        Un override cambia il comportamento di un singolo receiver verso un canale già collegato al
        suo gruppo: <strong>silenzia</strong> gli inoltri oppure <strong>sostituisce</strong> la
        soglia di gruppo con un'altra.
      </p>
      {error && <ErrorBanner error={error} />}
      <form onSubmit={(event) => void handleSubmit(event)}>
        <RequiredLegend />
        <div className="form-grid">
          <Field id="override-receiver" label="Receiver" required>
            <select
              id="override-receiver"
              required
              value={receiverId}
              onChange={(event) => setReceiverId(event.target.value)}
            >
              <option value="" disabled>
                Scegli un receiver
              </option>
              {receivers?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </Field>
          <Field id="override-channel" label="Canale" required>
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
          </Field>
          <Field id="override-mode" label="Modalità">
            <select
              id="override-mode"
              value={mode}
              onChange={(event) => setMode(event.target.value as OverrideMode)}
            >
              <option value="override">sostituisci la soglia</option>
              <option value="mute">silenzia</option>
            </select>
          </Field>
          {mode === "override" && (
            <Field id="override-severity" label="Soglia minima">
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
            </Field>
          )}
        </div>
        <div className="form-actions">
          <button
            type="submit"
            className="primary"
            disabled={!receiverId || !channelId || busy !== null}
          >
            {busy !== null ? "Salvataggio…" : "Salva override"}
          </button>
        </div>
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
  const { data: groups } = useQuery<GroupOut[], ApiError>({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });
  const [selectedGroupId, setSelectedGroupId] = useState<string>("");

  return (
    <div>
      <div className="page-header">
        <h1>Canali</h1>
      </div>
      <p className="page-subtitle">
        Dove NotifyHub inoltra le notifiche che superano una soglia: uno spazio Slack o Google Chat
        per volta, collegato ai gruppi che lo devono usare.
      </p>
      {error && <ErrorBanner error={error} />}

      {canManage && <CreateChannelForm />}

      <div className="card">
        <div className="card-header">
          <h3>Canali configurati</h3>
        </div>
        <div className="table-wrap">
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
        {channels && channels.length === 0 && (
          <p className="card-hint">Nessun canale configurato.</p>
        )}
      </div>

      {canManage && channels && (
        <div className="card">
          <div className="card-header">
            <h3>Soglie per gruppo</h3>
          </div>
          <p className="card-hint">
            Una notifica di un receiver del gruppo viene inoltrata a un canale quando la sua
            severity raggiunge la soglia scelta qui. «Non collegato» significa nessun inoltro.
          </p>
          <div className="form-row narrow">
            <label htmlFor="bindings-group">Gruppo</label>
            <select
              id="bindings-group"
              value={selectedGroupId}
              onChange={(event) => setSelectedGroupId(event.target.value)}
            >
              <option value="">Scegli un gruppo</option>
              {groups?.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
          {selectedGroupId && <ChannelBindings groupId={selectedGroupId} channels={channels} />}
        </div>
      )}

      {canManage && channels && <ReceiverOverrideForm channels={channels} />}
    </div>
  );
}
