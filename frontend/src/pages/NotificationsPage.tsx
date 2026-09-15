import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import type {
  ApiError,
  GroupOut,
  NotificationStatus,
  ReceiverOut,
  Severity,
  SeveritySource,
} from "../api/types";
import EmptyState from "../components/EmptyState";
import ErrorBanner from "../components/ErrorBanner";
import GroupList from "../components/GroupList";
import ReceiverNotificationsTable, {
  type ReceiverTableFilters,
} from "../components/ReceiverNotificationsTable";
import { SEVERITY_SOURCE_LABELS } from "../lib/severitySource";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info", "debug"];
// Origini filtrabili, nell'ordine della catena di severity. Le due della
// sorveglianza stanno in fondo e sono quelle che si cercano piu' spesso:
// "fammi vedere solo i job che non hanno inviato".
const SOURCES: SeveritySource[] = [
  "explicit",
  "exit_code",
  "duration",
  "rule",
  "preset_rule",
  "receiver_default",
  "missing",
  "recovered",
];

export default function NotificationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState(searchParams.get("q") ?? "");
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const groupId = searchParams.get("group_id") ?? undefined;
  const receiverId = searchParams.get("receiver_id") ?? undefined;
  const severityMin = (searchParams.get("severity_min") as Severity | null) ?? undefined;
  const status = (searchParams.get("status") as NotificationStatus | null) ?? undefined;
  const source = (searchParams.get("source") as SeveritySource | null) ?? undefined;
  // Le due dimensioni di stato stanno nell'URL come tutti gli altri filtri:
  // una vista filtrata resta condivisibile e sopravvive al ricaricamento.
  // Assente = qualsiasi; sono indipendenti e si combinano.
  const verifiedParam = searchParams.get("verified");
  const verified = verifiedParam === null ? undefined : verifiedParam === "true";

  function setFilter(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      return next;
    });
  }

  const {
    data: groups,
    isLoading: groupsLoading,
    error: groupsError,
  } = useQuery<GroupOut[], ApiError>({
    queryKey: ["groups"],
    queryFn: () => apiGet<GroupOut[]>("/api/v1/groups"),
  });

  // I receiver del gruppo aperto sono l'ossatura della pagina: una tabella per
  // ognuno, piu' il filtro che ne isola uno.
  const {
    data: receivers,
    isLoading: receiversLoading,
    error: receiversError,
  } = useQuery<ReceiverOut[], ApiError>({
    queryKey: ["group-receivers", groupId],
    queryFn: () => apiGet<ReceiverOut[]>(`/api/v1/groups/${groupId}/receivers`),
    enabled: !!groupId,
  });

  const currentGroup = groups?.find((g) => g.id === groupId);

  // Filtri comuni a tutte le tabelle. Il receiver non sta qui: lo mette ogni
  // tabella con il proprio.
  const filters: ReceiverTableFilters = {
    group_id: groupId,
    severity_min: severityMin,
    status,
    source,
    verified,
    q: q || undefined,
  };

  const visibleReceivers = (receivers ?? []).filter((r) => !receiverId || r.id === receiverId);

  async function runAction(name: string, action: () => Promise<void>) {
    setActionError(null);
    setBusyAction(name);
    try {
      await action();
    } catch (err) {
      setActionError(err as ApiError);
    } finally {
      setBusyAction(null);
    }
  }

  async function bulkRead() {
    await runAction("bulk", async () => {
      await apiPost("/api/v1/notifications/bulk-read", {
        ...filters,
        // Lo stesso filtro della vista: "segna tutte come lette" non deve toccare
        // cio' che i filtri stanno tenendo fuori, receiver compreso.
        receiver_id: receiverId,
      });
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    });
  }

  function selectGroup(groupId: string) {
    const next = new URLSearchParams(searchParams);
    next.set("group_id", groupId);
    // Il receiver appartiene al gruppo che si sta lasciando: tenerlo darebbe
    // una lista vuota senza spiegare perche'.
    next.delete("receiver_id");
    setSearchParams(next);
  }

  if (!groupId) {
    return (
      <div>
        <h1>Notifiche</h1>
        <p className="page-subtitle">
          Seleziona un gruppo per vedere le notifiche ricevute dal gruppo.
        </p>
        {groupsError && <ErrorBanner error={groupsError} />}
        <GroupList groups={groups ?? []} loading={groupsLoading} onSelect={selectGroup} />
      </div>
    );
  }

  return (
    <div>
      <Link to="/notifications" style={{ marginRight: 8, fontSize: 13 }}>
        ← Torna ai gruppi
      </Link>
      {/* Il nome del gruppo sta nel titolo, non solo nella query string: dentro
          la pagina si deve sapere in che gruppo si e' senza leggere l'URL. */}
      <h1>
        Notifiche <span className="title-separator">/</span>{" "}
        <span className="title-context">{currentGroup?.name ?? "Gruppo"}</span>
      </h1>
      {currentGroup?.description && <p className="page-subtitle">{currentGroup.description}</p>}
      {receiversError && <ErrorBanner error={receiversError} />}
      {actionError && <ErrorBanner error={actionError} />}

      <div className="toolbar">
        <select
          aria-label="Receiver del gruppo"
          value={receiverId ?? ""}
          onChange={(event) => setFilter("receiver_id", event.target.value)}
        >
          <option value="">Tutti i receiver</option>
          {(receivers ?? []).map((receiver) => (
            <option key={receiver.id} value={receiver.id}>
              {receiver.name}
              {receiver.status === "disabled" ? " (disabilitato)" : ""}
            </option>
          ))}
        </select>

        <select
          value={severityMin ?? ""}
          onChange={(event) => setFilter("severity_min", event.target.value)}
        >
          <option value="">Qualsiasi severity</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          aria-label="Origine della notifica"
          value={source ?? ""}
          onChange={(event) => setFilter("source", event.target.value)}
        >
          <option value="">Qualsiasi origine</option>
          {SOURCES.map((item) => (
            <option key={item} value={item}>
              {SEVERITY_SOURCE_LABELS[item]}
            </option>
          ))}
        </select>

        <select
          aria-label="Stato di lettura"
          value={status ?? ""}
          onChange={(event) => setFilter("status", event.target.value)}
        >
          <option value="">Lette e non lette</option>
          <option value="unread">Solo non lette</option>
          <option value="read">Solo lette</option>
        </select>

        <select
          aria-label="Stato di verifica"
          value={verifiedParam ?? ""}
          onChange={(event) => setFilter("verified", event.target.value)}
        >
          <option value="">Verificate e non</option>
          <option value="true">Solo verificate</option>
          <option value="false">Solo non verificate</option>
        </select>

        <input
          placeholder="Cerca nel contenuto…"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />

        <button disabled={busyAction !== null} onClick={() => void bulkRead()}>
          {busyAction === "bulk" ? "Aggiornamento…" : "Segna tutte come lette"}
        </button>
      </div>

      <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
        La ricerca esamina l'intero contenuto del messaggio. Per i payload archiviati su object
        storage esamina i primi 4096 caratteri.
      </p>

      {receiversLoading && <EmptyState message="Caricamento…" />}
      {!receiversLoading && visibleReceivers.length === 0 && (
        <EmptyState message="Nessun receiver in questo gruppo." />
      )}
      {visibleReceivers.map((receiver) => (
        <ReceiverNotificationsTable key={receiver.id} receiver={receiver} filters={filters} />
      ))}
    </div>
  );
}
