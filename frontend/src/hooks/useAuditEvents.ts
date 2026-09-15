import { type InfiniteData, useInfiniteQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import type { ApiError, AuditEventListOut, AuditOutcome } from "../api/types";

export interface AuditFilters {
  actor_user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  outcome?: AuditOutcome;
  // Solo sulla vista "letture e verifiche": ritrova anche i bulk-read, che
  // portano gli id dentro context (backend: indice GIN, migrazione 0016).
  notification_id?: string;
  from?: string;
  to?: string;
}

/** Stessa paginazione a cursore delle notifiche: l'API non offre la pagina per
 * numero, e su una tabella che cresce ogni giorno sarebbe la scelta sbagliata. */
export function useAuditEvents(path: string, filters: AuditFilters) {
  return useInfiniteQuery<
    AuditEventListOut,
    ApiError,
    InfiniteData<AuditEventListOut>,
    readonly unknown[],
    string | undefined
  >({
    queryKey: ["audit", path, filters],
    queryFn: ({ pageParam }) =>
      apiGet<AuditEventListOut>(path, { ...filters, cursor: pageParam, limit: 50 }),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}
