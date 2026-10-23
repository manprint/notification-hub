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
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import Field, { RequiredLegend, fieldAria } from "../components/Field";
import Modal from "../components/Modal";
import SeverityBadge from "../components/SeverityBadge";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { channelTypeLabel, formatDateTime, severityLabel } from "../lib/format";
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

/** Esempio di webhook nel campo: cambia con il tipo scelto, così chi incolla
 *  vede subito il formato giusto per quel servizio. */
function webhookPlaceholder(type: ChannelType): string {
  return type === "google_chat"
    ? "https://chat.googleapis.com/v1/spaces/…"
    : "https://hooks.slack.com/services/…";
}

function CreateChannelForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [type, setType] = useState<ChannelType>("slack");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; webhook?: string }>({});
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
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
      { success: `Canale «${name.trim()}» creato.` },
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
      <form className="form-stacked" noValidate onSubmit={(event) => void handleSubmit(event)}>
        <RequiredLegend />
        <Field id="channel-name" label="Nome" required error={fieldErrors.name}>
          <input
            {...fieldAria("channel-name", { error: fieldErrors.name })}
            required
            maxLength={255}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="channel-type" label="Tipo" required>
          <select
            id="channel-type"
            required
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
            placeholder={webhookPlaceholder(type)}
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

/** Modifica di un canale. È lei a rendere il Modal, così il dialogo sa quando
 *  un salvataggio è in corso e non si chiude a metà (come EditGroupForm). */
function EditChannelForm({ channel, onClose }: { channel: DeliveryChannelOut; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(channel.name);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; webhook?: string }>({});
  const { busy, error, run } = useAction();

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
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
    if (ok) onClose();
  }

  const nameId = `channel-edit-name-${channel.id}`;
  const webhookId = `channel-edit-webhook-${channel.id}`;

  return (
    <Modal title={`Modifica «${channel.name}»`} onClose={onClose} busy={busy !== null}>
      <form noValidate onSubmit={(event) => void handleSubmit(event)}>
        {error && <ErrorBanner error={error} />}
        <RequiredLegend />
        <Field id={nameId} label="Nome" required error={fieldErrors.name}>
          <input
            {...fieldAria(nameId, { error: fieldErrors.name })}
            required
            maxLength={255}
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
            value={webhookUrl}
            onChange={(event) => setWebhookUrl(event.target.value)}
          />
        </Field>
        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy !== null}>
            {busy !== null ? "Salvataggio…" : "Salva"}
          </button>
          <button type="button" disabled={busy !== null} onClick={onClose}>
            Annulla
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Le azioni di una riga (Prova, Attiva, Modifica, Elimina) con il loro stato:
 *  occupato, errore, dialoghi. L'esito della prova lo tiene la pagina, perché
 *  la colonna Diagnostica sta in un'altra cella della stessa riga. */
function ChannelActions({
  channel,
  onTested,
}: {
  channel: DeliveryChannelOut;
  onTested: (result: DeliveryChannelTestOut) => void;
}) {
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
        onTested(result);
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
          ? `Canale «${channel.name}» disattivato.`
          : `Canale «${channel.name}» attivato.`,
      },
    );
  }

  async function confirmDelete() {
    // Il dialogo si chiude solo se la cancellazione riesce: altrimenti l'errore
    // resta sotto gli occhi di chi ha confermato, nel dialogo stesso.
    const ok = await run(
      async () => {
        await apiDelete(`/api/v1/channels/${channel.id}`);
        await queryClient.invalidateQueries({ queryKey: ["channels"] });
        // Il backend cancella a cascata collegamenti ai gruppi, override e
        // storico consegne. Per prefisso, su ogni gruppo e ogni receiver: senza,
        // le tabelle gia' aperte restavano con una riga intestata all'UUID del
        // canale che non esiste piu'.
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["group-channel-bindings"] }),
          queryClient.invalidateQueries({ queryKey: ["receiver-overrides"] }),
          queryClient.invalidateQueries({ queryKey: ["deliveries"] }),
        ]);
      },
      { name: "delete", success: `Canale «${channel.name}» eliminato.` },
    );
    if (ok) setConfirmingDelete(false);
  }

  return (
    <>
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
      {actionError && !confirmingDelete && <ErrorBanner error={actionError} />}
      {editing && <EditChannelForm channel={channel} onClose={() => setEditing(false)} />}
      {confirmingDelete && (
        <ConfirmDialog
          title={`Elimina canale «${channel.name}»`}
          expectedText={channel.name}
          confirmLabel="Elimina canale"
          onConfirm={confirmDelete}
          onCancel={() => setConfirmingDelete(false)}
        >
          {actionError && <ErrorBanner error={actionError} />}
          <p>Verranno rimossi anche i collegamenti ai gruppi, gli override e lo storico consegne.</p>
        </ConfirmDialog>
      )}
    </>
  );
}

function ChannelDiagnostics({
  channel,
  testResult,
}: {
  channel: DeliveryChannelOut;
  testResult: DeliveryChannelTestOut | undefined;
}) {
  return (
    <div className="cell-diagnostics">
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
    </div>
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

  const columns: DataTableColumn<ReceiverChannelOverrideOut>[] = [
    { key: "channel", header: "Canale", render: (o) => channelName(o.channel_id) },
    {
      key: "mode",
      header: "Modalità",
      render: (o) => (o.mode === "mute" ? "Silenziato" : "Soglia sostituita"),
    },
    {
      key: "severity",
      header: "Soglia minima",
      render: (o) => (o.min_severity ? <SeverityBadge severity={o.min_severity} /> : "—"),
    },
    {
      key: "actions",
      header: "",
      render: (o) => (
        <div className="row-actions">
          <button
            className="danger"
            disabled={busy !== null}
            onClick={() => void remove(o.channel_id)}
          >
            {busy === o.channel_id ? "Rimozione…" : "Rimuovi"}
          </button>
        </div>
      ),
    },
  ];

  return (
    <>
      {error && <ErrorBanner error={error} />}
      {actionError && <ErrorBanner error={actionError} />}
      <DataTable
        caption="Override del receiver"
        columns={columns}
        rows={overrides ?? []}
        rowKey={(o) => o.id}
        loading={!overrides && !error}
        error={error}
        emptyMessage="Nessun override per questo receiver: valgono le soglie di gruppo."
      />
    </>
  );
}

/** Etichetta del receiver nel selettore: "gruppo / receiver". Il solo nome non
 *  basta, due gruppi possono avere entrambi un receiver "backup". */
function receiverLabel(receiver: ReceiverOut, groupNames: Map<string, string>): string {
  const group = groupNames.get(receiver.group_id);
  return group ? `${group} / ${receiver.name}` : receiver.name;
}

function ReceiverOverrideForm({
  channels,
  groups,
}: {
  channels: DeliveryChannelOut[];
  groups: GroupOut[];
}) {
  const [receiverId, setReceiverId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [mode, setMode] = useState<OverrideMode>("override");
  const [minSeverity, setMinSeverity] = useState<Severity>("error");
  const queryClient = useQueryClient();
  const { busy, error, run, clearError } = useAction();

  // Il receiver si sceglie da un elenco: prima era un campo di testo libero in
  // cui incollare un UUID a mano, e qualunque valore non-UUID faceva rispondere
  // 500 all'API.
  const { data: receivers } = useQuery<ReceiverOut[], ApiError>({
    queryKey: ["receivers-all"],
    queryFn: () => apiGet<ReceiverOut[]>("/api/v1/receivers"),
  });

  const groupNames = new Map(groups.map((g) => [g.id, g.name]));
  const receiverOptions = (receivers ?? [])
    .map((r) => ({ id: r.id, label: receiverLabel(r, groupNames) }))
    .sort((a, b) => a.label.localeCompare(b.label, "it"));

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
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
              onChange={(event) => {
                setReceiverId(event.target.value);
                // L'errore di un salvataggio appartiene al receiver di prima.
                clearError();
              }}
            >
              <option value="" disabled>
                Scegli un receiver
              </option>
              {receiverOptions.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
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
              <option value="override">Soglia sostituita</option>
              <option value="mute">Silenziato</option>
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
                    {severityLabel(s)}
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
          {/* key: cambiando receiver il pannello riparte da zero, senza l'errore
              di un'azione sul receiver di prima. */}
          <ReceiverOverridesPanel key={receiverId} receiverId={receiverId} channels={channels} />
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
  const [testResults, setTestResults] = useState<Record<string, DeliveryChannelTestOut>>({});

  const channelColumns: DataTableColumn<DeliveryChannelOut>[] = [
    { key: "name", header: "Nome", render: (c) => c.name },
    { key: "type", header: "Tipo", render: (c) => channelTypeLabel(c.type) },
    { key: "webhook", header: "Webhook", render: (c) => <code>{c.webhook_hint}</code> },
    {
      key: "status",
      header: "Stato",
      render: (c) => (
        <span className={c.enabled ? "status-pill ok" : "status-pill warn"}>
          {c.enabled ? "Attivo" : "Disattivo"}
        </span>
      ),
    },
    {
      key: "diagnostics",
      header: "Diagnostica",
      render: (c) => <ChannelDiagnostics channel={c} testResult={testResults[c.id]} />,
    },
    {
      key: "actions",
      header: "",
      render: (c) =>
        canManage ? (
          <ChannelActions
            channel={c}
            onTested={(result) => setTestResults((prev) => ({ ...prev, [c.id]: result }))}
          />
        ) : null,
    },
  ];

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
        <DataTable
          caption="Canali configurati"
          columns={channelColumns}
          rows={channels ?? []}
          rowKey={(c) => c.id}
          loading={!channels && !error}
          error={error}
          emptyMessage="Nessun canale configurato."
        />
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
          {/* key: cambiando gruppo, riga appena salvata ed errore dell'ultima
              azione restano al gruppo di prima. */}
          {selectedGroupId && (
            <ChannelBindings key={selectedGroupId} groupId={selectedGroupId} channels={channels} />
          )}
        </div>
      )}

      {canManage && channels && <ReceiverOverrideForm channels={channels} groups={groups ?? []} />}
    </div>
  );
}
