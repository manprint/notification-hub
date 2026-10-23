import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { apiPatch, apiPost } from "../api/client";
import type {
  NotificationListItemOut,
  NotificationListOut,
  NotificationStatus,
  ReceiverOut,
} from "../api/types";
import { useAction } from "../hooks/useAction";
import { type NotificationFilters, useNotifications } from "../hooks/useNotifications";
import { useSession } from "../hooks/useSession";
import { formatBytes, formatDate, formatTime, severityLabel } from "../lib/format";
import { MEMBER_ROLES, hasRole } from "../lib/roles";
import { isSurveillanceSource, phaseLabel, severitySourceLabel } from "../lib/severitySource";
import DataTable, { type DataTableColumn } from "./DataTable";
import ErrorBanner from "./ErrorBanner";
import SeverityBadge from "./SeverityBadge";
import StatusPill from "./StatusPill";

/** I filtri della pagina, meno il receiver: quello lo decide questa tabella. */
export type ReceiverTableFilters = Omit<NotificationFilters, "receiver_id">;

/**
 * Le notifiche di UN receiver del gruppo.
 *
 * Una tabella per receiver e non una tabella sola raggruppata a video: ogni
 * tabella ha il proprio cursore e il proprio "Carica altri", quindi la prima
 * pagina di un receiver e' davvero la sua. Con un cursore unico di gruppo, un
 * receiver molto attivo riempirebbe la pagina e gli altri resterebbero vuoti
 * pur avendo notifiche piu' vecchie da mostrare.
 */
export default function ReceiverNotificationsTable({
  receiver,
  filters,
}: {
  receiver: ReceiverOut;
  filters: ReceiverTableFilters;
}) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const { busy: busyAction, error: actionError, run } = useAction();
  const { role } = useSession();
  // Segnare letta/verificata e aprire la pagina del receiver sono da member in
  // su (require_member nel backend, RequireRole sulla rotta /receivers/:id): al
  // viewer si mostrano i dati, non pulsanti che risponderebbero 403 o un link
  // verso una pagina che non puo' aprire.
  const canManage = hasRole(role, MEMBER_ROLES);
  // Con il filtro "solo lette" non c'e' niente da segnare come letto: il
  // pulsante sparisce invece di restare li' a non fare niente.
  const canBulkRead = canManage && filters.status !== "read";

  const { data, isLoading, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useNotifications({ ...filters, receiver_id: receiver.id });

  const rows = data?.pages.flatMap((page: NotificationListOut) => page.notifications) ?? [];

  // Solo le notifiche di questo receiver: le tabelle degli altri restano com'erano.
  // La chiave parziale `{ receiver_id }` le abbraccia tutte (pagine comprese).
  function invalidaNotifiche() {
    return queryClient.invalidateQueries({
      queryKey: ["notifications", { receiver_id: receiver.id }],
    });
  }

  async function setStatus(id: string, status: NotificationStatus) {
    await run(
      async () => {
        await apiPatch(`/api/v1/notifications/${id}`, { status });
        await invalidaNotifiche();
        // Il conteggio "non lette" del gruppo sta nella griglia dei gruppi.
        await queryClient.invalidateQueries({ queryKey: ["groups"] });
      },
      {
        name: `status:${id}`,
        success:
          status === "read" ? "Notifica segnata come letta." : "Notifica riportata a non letta.",
      },
    );
  }

  async function setVerified(id: string, verified: boolean) {
    await run(
      async () => {
        await apiPatch(`/api/v1/notifications/${id}`, { verified });
        await invalidaNotifiche();
      },
      {
        name: `verified:${id}`,
        success: verified
          ? "Notifica segnata come verificata."
          : "Verifica rimossa dalla notifica.",
      },
    );
  }

  async function bulkRead() {
    await run(
      async () => {
        await apiPost("/api/v1/notifications/bulk-read", {
          // Tutti i filtri della tabella, stato compreso, piu' il suo receiver:
          // il pulsante non deve toccare cio' che la tabella sta tenendo fuori
          // dalla vista.
          ...filters,
          receiver_id: receiver.id,
        });
        await invalidaNotifiche();
        await queryClient.invalidateQueries({ queryKey: ["groups"] });
      },
      { name: "bulk", success: `Notifiche di ${receiver.name} segnate come lette.` },
    );
  }

  // Le azioni di riga hanno tutte lo stesso testo: il nome accessibile dice
  // anche quale notifica tocca (ora e severity), e inizia col testo visibile.
  function descrizioneRiga(n: NotificationListItemOut): string {
    return `${formatDate(n.received_at)} ${formatTime(n.received_at)}, ${severityLabel(n.severity)}`;
  }

  const columns: DataTableColumn<NotificationListItemOut>[] = [
    { key: "severity", header: "Severity", render: (n) => <SeverityBadge severity={n.severity} /> },
    {
      key: "content",
      header: "Contenuto",
      // Un link "Apri" e non il testo del messaggio: la lista non e' il posto
      // dove si legge un log, e una preview lunga sfonda la riga. Le pill
      // restano perche' sono segnali sul payload (testo alterato in ingestion,
      // corpo su object storage) che altrimenti si vedrebbero solo entrando.
      // Lo stato porta la pagina d'origine: il ritorno dal dettaglio riapre
      // questo gruppo con i suoi filtri.
      render: (n) => (
        <div className="content-cell">
          <Link
            to={`/notifications/${n.id}`}
            state={{ from: `${location.pathname}${location.search}` }}
            aria-label={`Apri la notifica di ${descrizioneRiga(n)}`}
          >
            Apri
          </Link>
          {n.content_normalized && <span className="status-pill">contenuto normalizzato</span>}
          {n.storage_backend === "object" && (
            <span className="status-pill" title={`${n.content_size} byte`}>
              {formatBytes(n.content_size)} su object storage
            </span>
          )}
        </div>
      ),
    },
    {
      key: "source",
      header: "Origine",
      render: (n) => (
        <span className="status-cell">
          <span
            className="status-pill"
            title={
              isSurveillanceSource(n.severity_source)
                ? "Notifica scritta da NotifyHub: nessuno l'ha inviata"
                : `Severity decisa da: ${severitySourceLabel(n.severity_source)}`
            }
          >
            {severitySourceLabel(n.severity_source)}
          </span>
          {n.phase === "start" && (
            <span
              className="status-pill info"
              title="Ping di avvio: l'esito arriva a fine esecuzione"
            >
              {phaseLabel(n.phase)}
            </span>
          )}
        </span>
      ),
    },
    {
      key: "status",
      header: "Stato",
      render: (n) => (
        <div className="status-cell">
          <StatusPill status={n.status} />
          <span className={`status-pill${n.verified ? " verified" : ""}`}>
            {n.verified ? "Verificata" : "Non verificata"}
          </span>
        </div>
      ),
    },
    {
      key: "received_at",
      header: "Ricevuta",
      render: (n) => (
        <span className="received-at">
          <span>{formatDate(n.received_at)}</span>
          <span>{formatTime(n.received_at)}</span>
        </span>
      ),
    },
  ];
  if (canManage) {
    columns.push({
      key: "actions",
      header: "",
      render: (n) => (
        <div className="row-actions">
          <button
            aria-label={`${n.status === "unread" ? "Segna come letta" : "Segna come non letta"}: ${descrizioneRiga(n)}`}
            disabled={busyAction !== null}
            onClick={() => void setStatus(n.id, n.status === "unread" ? "read" : "unread")}
          >
            {n.status === "unread" ? "Segna come letta" : "Segna come non letta"}
          </button>
          <button
            aria-label={`${n.verified ? "Segna come non verificata" : "Segna come verificata"}: ${descrizioneRiga(n)}`}
            disabled={busyAction !== null}
            onClick={() => void setVerified(n.id, !n.verified)}
          >
            {n.verified ? "Segna come non verificata" : "Segna come verificata"}
          </button>
        </div>
      ),
    });
  }

  return (
    <section className="card" aria-label={`Notifiche di ${receiver.name}`}>
      <div className="receiver-table-header">
        <h3>
          {canManage ? <Link to={`/receivers/${receiver.id}`}>{receiver.name}</Link> : receiver.name}
          {receiver.status === "disabled" && <span className="status-pill warn">disabilitato</span>}
        </h3>
        {/* Il testo resta quello del pulsante di gruppo, ma il nome accessibile
            dice su quale receiver agisce: due pulsanti identici nella stessa
            pagina, con scope diverso, sono indistinguibili da tastiera. */}
        {canBulkRead && (
          <button
            aria-label={`Segna tutte come lette: ${receiver.name}`}
            disabled={busyAction !== null}
            onClick={() => void bulkRead()}
          >
            {busyAction === "bulk" ? "Aggiornamento…" : "Segna tutte come lette"}
          </button>
        )}
      </div>

      {error && <ErrorBanner error={error} />}
      {actionError && <ErrorBanner error={actionError} />}

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(n) => n.id}
        loading={isLoading}
        error={error}
        hasMore={hasNextPage}
        loadingMore={isFetchingNextPage}
        onLoadMore={() => void fetchNextPage()}
        emptyMessage="Nessuna notifica trovata."
      />
    </section>
  );
}
