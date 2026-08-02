import { type InfiniteData, useInfiniteQuery } from "@tanstack/react-query";
import { apiGet } from "../api/client";
import type { ApiError, NotificationListOut, NotificationStatus, Severity } from "../api/types";

export interface NotificationFilters {
  group_id?: string;
  receiver_id?: string;
  status?: NotificationStatus;
  severity_min?: Severity;
  q?: string;
  from?: string;
  to?: string;
}

export function useNotifications(filters: NotificationFilters) {
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
  });
}
