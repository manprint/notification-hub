import { type InfiniteData, useInfiniteQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import type {
  ApiError,
  NotificationListOut,
  NotificationStatus,
  Severity,
  SeveritySource,
} from "../api/types";

export interface NotificationFilters {
  group_id?: string;
  receiver_id?: string;
  status?: NotificationStatus;
  severity_min?: Severity;
  // Chi ha deciso la severity: serve a isolare gli allarmi scritti dalla
  // sorveglianza (missing/recovered) dai messaggi inviati davvero.
  source?: SeveritySource;
  // Revisione manuale, indipendente da `status`: i due filtri si combinano.
  verified?: boolean;
  q?: string;
  from?: string;
  to?: string;
}

export function useNotifications(
  filters: NotificationFilters,
  options?: { enabled?: boolean },
) {
  return useInfiniteQuery<
    NotificationListOut,
    ApiError,
    InfiniteData<NotificationListOut>,
    readonly unknown[],
    string | undefined
  >({
    queryKey: ["notifications", filters],
    queryFn: ({ pageParam }) =>
      apiGet<NotificationListOut>("/api/v1/notifications", {
        ...filters,
        cursor: pageParam,
        limit: 20,
      }),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: options?.enabled ?? true,
  });
}
