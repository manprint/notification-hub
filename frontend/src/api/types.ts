// Rispecchia gli schemi Pydantic del backend: stessi nomi di campo JSON,
// nessuna conversione a camelCase (fonte di bug silenziosi).

export type Severity = "critical" | "error" | "warning" | "info" | "debug";
export type NotificationStatus = "unread" | "read";
export type DeliveryStatus = "pending" | "sending" | "sent" | "failed" | "dead";
export type ChannelType = "slack" | "google_chat" | "generic_webhook";
export type UserRole = "owner" | "admin" | "member" | "viewer";
export type UserStatus = "active" | "disabled";
export type ReceiverStatus = "active" | "disabled";
export type TenantStatus = "active" | "suspended";
export type OverrideMode = "override" | "mute";

export interface ApiError {
  status: number;
  type: string;
  title: string;
  detail: string;
  extra: Record<string, unknown>;
}

export interface TokenPairOut {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface MeOut {
  id: string;
  email: string;
  role: UserRole;
  tenant_id: string;
  tenant_name: string;
}

export interface UserOut {
  id: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  last_login_at: string | null;
}

export interface InvitationOut {
  id: string;
  email: string;
  role: UserRole;
  expires_at: string;
  invite_url: string;
  email_sent: boolean;
}

export interface InvitationSummaryOut {
  id: string;
  email: string;
  role: UserRole;
  expires_at: string;
  accepted_at: string | null;
}

export interface GroupOut {
  id: string;
  name: string;
  description: string | null;
}

export interface GroupChannelBindingOut {
  id: string;
  group_id: string;
  channel_id: string;
  min_severity: Severity;
  enabled: boolean;
}

export interface ReceiverChannelOverrideOut {
  id: string;
  receiver_id: string;
  channel_id: string;
  mode: OverrideMode;
  min_severity: Severity | null;
}

export interface ReceiverOut {
  id: string;
  group_id: string;
  slug: string;
  name: string;
  status: ReceiverStatus;
  ingestion_module: string;
  default_severity: Severity;
  max_body_bytes: number;
  rate_limit_per_min: number;
  rejected_last_24h?: number;
}

export interface SeverityRuleOut {
  id: string;
  receiver_id: string;
  priority: number;
  pattern: string;
  case_insensitive: boolean;
  severity: Severity;
  enabled: boolean;
}

export interface TestSeverityOut {
  severity: Severity;
  source: string;
  matched_rule_id: string | null;
  matched_pattern: string | null;
}

export interface DeleteImpactOut {
  receivers: number;
  notifications: number;
  deliveries: number;
}

export interface DeliveryChannelOut {
  id: string;
  name: string;
  type: ChannelType;
  webhook_hint: string;
  enabled: boolean;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error: string | null;
}

export interface DeliveryChannelTestOut {
  sent: boolean;
  detail: string;
}

export interface DeliveryOut {
  id: string;
  notification_id: string;
  channel_id: string;
  status: DeliveryStatus;
  attempts: number;
  next_attempt_at: string;
  locked_at: string | null;
  response_code: number | null;
  last_error: string | null;
  sent_at: string | null;
}

export interface NotificationListItemOut {
  id: string;
  receiver_id: string;
  content_preview: string;
  content_size: number;
  content_normalized: boolean;
  storage_backend: "inline" | "object";
  severity: Severity;
  severity_source: string;
  status: NotificationStatus;
  received_at: string;
}

export interface NotificationListOut {
  notifications: NotificationListItemOut[];
  next_cursor: string | null;
  unread_count: number;
}

export interface NotificationDetailOut {
  id: string;
  receiver_id: string;
  content: string | null;
  content_url: string | null;
  content_preview: string;
  content_size: number;
  content_normalized: boolean;
  severity: Severity;
  severity_source: string;
  matched_pattern: string | null;
  status: NotificationStatus;
  received_at: string;
  source_ip: string | null;
}

export interface StatsSummaryOut {
  total_unread: number;
  by_severity: Record<string, number>;
  by_group: Array<{
    group_id: string;
    group_name: string;
    total: number;
    unread_count: number;
  }>;
  notifications_last_24h: number;
  deliveries_dead: number;
}

export interface TenantOut {
  id: string;
  name: string;
  slug: string;
  max_body_bytes: number;
  max_notifications_per_day: number | null;
  max_storage_bytes: number | null;
  retention_days: number | null;
  status: TenantStatus;
}
