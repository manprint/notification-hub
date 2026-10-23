import { type InfiniteData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import type {
  ApiError,
  DeliveryChannelOut,
  DeliveryListOut,
  DeliveryOut,
  DeliveryStatus,
} from "../api/types";
import DataTable, { type DataTableColumn } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import SeverityBadge from "../components/SeverityBadge";
import StatusPill, { statusLabel } from "../components/StatusPill";
import { useAction } from "../hooks/useAction";
import { useSession } from "../hooks/useSession";
import { formatDate, formatDateTime, formatTime } from "../lib/format";
import { MEMBER_ROLES, hasRole } from "../lib/roles";

const STATUSES: DeliveryStatus[] = ["pending", "sending", "sent", "failed", "dead"];

const STATUS_HELP: Record<DeliveryStatus, string> = {
  pending: "in coda, non ancora inviata",
  sending: "invio in corso",
  sent: "consegnata al webhook",
  failed: "tentativo fallito, ritenta in automatico",
  dead: "esauriti i tentativi, serve un ri-accodamento manuale",
};

// Solo in questi due stati `next_attempt_at` e' un appuntamento: una consegna
// morta non ritenta piu' da sola, una in invio lo sta gia' facendo.
const WAITING_RETRY: DeliveryStatus[] = ["pending", "failed"];

// Una morta per 4xx non ritenta mai: il webhook l'ha rifiutata al primo colpo, con
// attempts che può anche essere 0. Il 429 invece si ritenta, quindi resta fuori.
function motivoStato(d: DeliveryOut): string {
  const codice = d.response_code;
  if (d.status === "dead" && codice !== null && codice >= 400 && codice < 500 && codice !== 429) {
    return (
      `rifiutata dal webhook (HTTP ${codice}), nessun tentativo ripetuto; ` +
      "serve un ri-accodamento manuale"
    );
  }
  return STATUS_HELP[d.status] ?? "stato non riconosciuto da questa versione";
}

const PAGE_SIZE = 100;

// Canali che compaiono nelle consegne caricate, per il filtro del viewer. Se il
// filtro attivo non ha righe, il canale selezionato resta comunque nella tendina.
function opzioniCanaliDelleConsegne(
  consegne: DeliveryOut[],
  canaleSelezionato: string | undefined,
): { id: string; name: string }[] {
  const opzioni = new Map<string, string>();
  for (const d of consegne) {
    if (!opzioni.has(d.channel_id)) opzioni.set(d.channel_id, d.channel_name);
  }
  if (canaleSelezionato && !opzioni.has(canaleSelezionato)) {
    opzioni.set(canaleSelezionato, "Canale selezionato");
  }
  return [...opzioni].map(([id, name]) => ({ id, name }));
}

export default function DeliveriesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const status = (searchParams.get("status") as DeliveryStatus | null) ?? undefined;
  const channelId = searchParams.get("channel_id") ?? undefined;
  const queryClient = useQueryClient();
  const { role } = useSession();
  const { busy: retryingId, error: actionError, run } = useAction();

  // Paginazione a cursore, come le notifiche e l'audit: lo storico cresce a
  // ogni inoltro, e la lista nuda si fermava alle prime 100 righe senza dirlo.
  // I filtri stanno nella chiave: cambiarli riparte dalla prima pagina.
  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery<
      DeliveryListOut,
      ApiError,
      InfiniteData<DeliveryListOut>,
      readonly unknown[],
      string | undefined
    >({
      queryKey: ["deliveries", { status, channel_id: channelId }],
      queryFn: ({ pageParam }) =>
        apiGet<DeliveryListOut>("/api/v1/deliveries", {
          status,
          channel_id: channelId,
          cursor: pageParam,
          limit: PAGE_SIZE,
        }),
      initialPageParam: undefined,
      getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    });

  const rows = data?.pages.flatMap((page) => page.deliveries) ?? [];

  // La lista dei canali (URL mascherato, ultimo errore) e' riservata a member e
  // superiori: il viewer non la chiede, e filtra per i canali delle consegne caricate.
  const canVedereCanali = hasRole(role, MEMBER_ROLES);
  const { data: channels, error: channelsError } = useQuery<DeliveryChannelOut[], ApiError>({
    queryKey: ["channels"],
    queryFn: () => apiGet<DeliveryChannelOut[]>("/api/v1/channels"),
    enabled: canVedereCanali,
  });
  const opzioniCanale = canVedereCanali
    ? (channels ?? []).map((c) => ({ id: c.id, name: c.name }))
    : opzioniCanaliDelleConsegne(rows, channelId);
  // Un canale nell'URL senza una voce in tendina (lista non caricata, canale
  // cancellato): la tendina non deve mostrare "Tutti i canali" mentre la lista
  // resta filtrata.
  if (channelId && !opzioniCanale.some((c) => c.id === channelId)) {
    opzioniCanale.push({ id: channelId, name: "Canale selezionato" });
  }

  function setParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  }

  async function retry(id: string) {
    await run(
      async () => {
        const aggiornata = await apiPost<DeliveryOut>(`/api/v1/deliveries/${id}/retry`);
        // La risposta dice com'è la consegna adesso: la riga si aggiorna nelle
        // pagine già caricate. Rileggerle tutte costava una richiesta per
        // pagina ("Carica altri" ne accumula molte). Una riga che il filtro di
        // stato non contiene più esce dalla lista.
        const liste = queryClient.getQueriesData<InfiniteData<DeliveryListOut>>({
          queryKey: ["deliveries"],
        });
        for (const [key] of liste) {
          const filtro = key[1] as { status?: DeliveryStatus } | undefined;
          const fuori = filtro?.status !== undefined && filtro.status !== aggiornata.status;
          queryClient.setQueryData<InfiniteData<DeliveryListOut>>(key, (old) =>
            old
              ? {
                  ...old,
                  pages: old.pages.map((page) => ({
                    ...page,
                    deliveries: fuori
                      ? page.deliveries.filter((d) => d.id !== id)
                      : page.deliveries.map((d) => (d.id === id ? aggiornata : d)),
                  })),
                }
              : old,
          );
        }
        // Il riepilogo conta le consegne morte: va riletto.
        await queryClient.invalidateQueries({ queryKey: ["stats-summary"] });
      },
      { name: id, success: "Consegna rimessa in coda." },
    );
  }

  const canRetry = hasRole(role, MEMBER_ROLES);
  const filtriAttivi = [status, channelId].filter(Boolean).length;

  const columns: DataTableColumn<DeliveryOut>[] = [
    // Stesse colonne dell'elenco delle notifiche, nello stesso ordine: la
    // severity ha la sua colonna e si scorre in verticale, invece di stare in
    // mezzo al testo di un'altra cella.
    { key: "severity", header: "Severity", render: (d) => <SeverityBadge severity={d.severity} /> },
    {
      key: "notification",
      header: "Notifica inoltrata",
      // Un link "Apri" e non il testo del messaggio, come nell'elenco delle
      // notifiche: il corpo si legge nella sua pagina, e una preview lunga
      // sfonda la riga e spinge fuori vista le colonne che dicono com'e'
      // andata la consegna.
      render: (d) => (
        <div className="cell-preview">
          <div className="content-cell">
            <Link
              to={`/notifications/${d.notification_id}`}
              state={{ from: `${location.pathname}${location.search}` }}
              aria-label={`Apri la notifica ricevuta ${formatDate(d.received_at)} ${formatTime(d.received_at)}`}
            >
              Apri
            </Link>
          </div>
          <div className="cell-diagnostics">da {d.receiver_name}</div>
        </div>
      ),
    },
    { key: "channel_name", header: "Canale", render: (d) => d.channel_name },
    {
      key: "status",
      header: "Stato",
      render: (d) => (
        <div className="cell-preview">
          <StatusPill status={d.status} />
          <div className="cell-diagnostics">
            {motivoStato(d)}
          </div>
        </div>
      ),
    },
    {
      key: "attempts",
      header: "Tentativi",
      render: (d) => (
        <div className="cell-preview">
          {d.attempts}
          {d.sent_at && (
            <div className="cell-diagnostics">inviata: {formatDateTime(d.sent_at)}</div>
          )}
          {WAITING_RETRY.includes(d.status) && (
            <div className="cell-diagnostics">
              prossimo tentativo: {formatDateTime(d.next_attempt_at)}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "last_error",
      header: "Esito",
      render: (d) => {
        const codice = d.response_code ? `HTTP ${d.response_code}` : null;
        // Il messaggio del backend comincia spesso con "HTTP 404: ...": il codice non si ripete.
        const giaNelErrore =
          codice !== null &&
          d.last_error !== null &&
          (d.last_error === codice || d.last_error.startsWith(`${codice}:`));
        return (
          <div className="cell-diagnostics">
            {!giaNelErrore && (codice ?? "—")}
            {d.last_error && <div>{d.last_error}</div>}
          </div>
        );
      },
    },
    {
      key: "received_at",
      header: "Ricevuta",
      render: (d) => (
        <span className="received-at">
          <span>{formatDate(d.received_at)}</span>
          <span>{formatTime(d.received_at)}</span>
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (d) =>
        d.status === "dead" && canRetry ? (
          <div className="row-actions">
            <button disabled={retryingId !== null} onClick={() => void retry(d.id)}>
              {retryingId === d.id ? "Ri-accodamento…" : "Ri-accoda"}
            </button>
          </div>
        ) : null,
    },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>Consegne</h1>
      </div>
      <p className="page-subtitle">
        Storico degli inoltri verso Slack e Google Chat: una riga per ogni notifica spedita a un
        canale. Serve a capire perché un messaggio non è arrivato — codice HTTP, errore e
        tentativi. Le consegne in stato «morta» sono finite dopo i tentativi o perché rifiutate dal
        webhook, e si ri-accodano a mano.
      </p>
      {error && <ErrorBanner error={error} />}
      {actionError && <ErrorBanner error={actionError} />}

      <div className="card">
        <div className="filters">
          <div className="form-row">
            <label htmlFor="delivery-status">Stato della consegna</label>
            <select
              id="delivery-status"
              value={status ?? ""}
              onChange={(event) => setParam("status", event.target.value)}
            >
              <option value="">Tutti gli stati</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <label htmlFor="delivery-channel">Canale</label>
            <select
              id="delivery-channel"
              value={channelId ?? ""}
              onChange={(event) => setParam("channel_id", event.target.value)}
            >
              <option value="">Tutti i canali</option>
              {opzioniCanale.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          {filtriAttivi > 0 && (
            <div className="filters-actions">
              <button onClick={() => setSearchParams(new URLSearchParams())}>
                Azzera i filtri ({filtriAttivi})
              </button>
            </div>
          )}
        </div>
        {channelsError && <ErrorBanner error={channelsError} />}
      </div>

      <div className="card">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(d) => d.id}
          loading={isLoading}
          error={error}
          // Con un filtro attivo la frase sulla soglia non c'entra: il messaggio
          // dice che il filtro non trova nulla, non che il sistema è fermo.
          emptyMessage={
            filtriAttivi > 0
              ? "Nessuna consegna con questi filtri."
              : "Nessuna consegna trovata: nessuna notifica ha ancora superato la soglia di un canale."
          }
          hasMore={hasNextPage}
          onLoadMore={() => void fetchNextPage()}
          loadingMore={isFetchingNextPage}
        />
      </div>
    </div>
  );
}
