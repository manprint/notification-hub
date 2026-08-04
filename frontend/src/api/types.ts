// Rispecchia gli schemi Pydantic del backend: stessi nomi di campo JSON,
// nessuna conversione a camelCase (fonte di bug silenziosi).

export type Severity = "critical" | "error" | "warning" | "info" | "debug";
export type NotificationStatus = "unread" | "read";
export type DeliveryStatus = "pending" | "sending" | "sent" | "failed" | "dead";
// Solo i due tipi previsti dall'enum channel_type del database: un terzo
// valore lato UI produceva sempre e solo un 422 al salvataggio.
export type ChannelType = "slack" | "google_chat";
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
  group_ids: string[];
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

// Passo della catena che ha deciso la severity di una notifica. "preset_rule"
// distingue una regola arrivata da un preset condiviso da una scritta sul
// receiver: dice dove andare a correggerla.
export type SeveritySource =
  | "explicit"
  | "exit_code"
  | "duration"
  // Notifiche scritte dal server, non inviate da nessuno: la sorveglianza
  // dell'attesa segnala l'invio che non e' arrivato (`missing`) e la ripresa
  // degli invii dopo un'assenza (`recovered`).
  | "missing"
  | "recovered"
  | "rule"
  | "preset_rule"
  | "receiver_default";

/** Fase dichiarata dal mittente nell'header X-Phase. `null` = non dichiarata:
 *  tutto lo storico e qualunque invio fatto a mano. */
export type NotificationPhase = "start" | "end";

export interface ReceiverOut {
  id: string;
  group_id: string;
  // `gruppo-receiver-token`: il prefisso e' leggibile, gli ultimi 22 caratteri
  // sono la credenziale casuale.
  slug: string;
  // URL completa di invio, decisa dal backend sulla richiesta in corso (reverse
  // proxy e https compresi) e identica a quella scritta nello script scaricabile.
  ingest_url: string;
  name: string;
  status: ReceiverStatus;
  ingestion_module: string;
  default_severity: Severity;
  // null = l'header X-Exit-Code non influenza la severity.
  exit_code_severity: Severity | null;
  // Le due viaggiano in coppia: null su entrambe = la durata dell'esecuzione
  // (header X-Duration-Ms) non influenza la severity. Il backend rifiuta con
  // 422 una coppia con una sola delle due valorizzata.
  duration_threshold_seconds: number | null;
  duration_severity: Severity | null;
  max_body_bytes: number;
  rate_limit_per_min: number;
  rejected_last_24h?: number;
  // Sorveglianza dell'attesa (dead man's switch): ogni quanto ci si aspetta un
  // invio. Uno solo fra intervallo ed espressione cron; null su tutto =
  // sorveglianza spenta.
  expected_every_seconds: number | null;
  expected_cron: string | null;
  expected_timezone: string | null;
  expected_grace_seconds: number | null;
  missing_severity: Severity | null;
  // Stato, calcolato dal server: la scadenza col cron e il suo fuso non si
  // calcola nel browser.
  last_notification_at: string | null;
  // Ultimo ping di avvio: distingue "non e partito" da "partito e mai finito".
  last_start_at: string | null;
  missing_alerted_at: string | null;
  expected_since: string | null;
  expected_deadline_at: string | null;
  expected_late: boolean;
}

export interface SeverityReplayItemOut {
  notification_id: string;
  received_at: string;
  content_preview: string;
  truncated: boolean;
  stored_severity: Severity;
  stored_source: string;
  replayed_severity: Severity;
  replayed_source: string;
  matched_rule_id: string | null;
  matched_pattern: string | null;
  matched_preset_name: string | null;
  changed: boolean;
}

export interface SeverityReplayOut {
  items: SeverityReplayItemOut[];
  changed_count: number;
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
  matched_preset_id?: string | null;
  matched_preset_name?: string | null;
  // Vero anche quando la severity l'ha decisa un altro passo: dice che la durata
  // simulata avrebbe comunque sforato la soglia.
  duration_exceeded?: boolean;
}

export interface SeverityPresetRuleOut {
  id: string;
  preset_id: string;
  priority: number;
  pattern: string;
  case_insensitive: boolean;
  severity: Severity;
  enabled: boolean;
}

export interface SeverityPresetOut {
  id: string;
  // null = preset creato a mano, non nato da una voce del catalogo.
  builtin_key: string | null;
  name: string;
  description: string;
  rules_count: number;
  receivers_count: number;
}

export interface SeverityPresetDetailOut extends SeverityPresetOut {
  rules: SeverityPresetRuleOut[];
}

export interface BuiltinPresetOut {
  key: string;
  name: string;
  description: string;
  rules_count: number;
  installed: boolean;
}

export interface SyncBuiltinPresetsOut {
  installed: string[];
  already_present: string[];
}

export interface ReceiverPresetOut {
  preset_id: string;
  name: string;
  description: string;
  builtin_key: string | null;
  position: number;
  rules_count: number;
}

export interface SeverityChainItemOut {
  position: number;
  rule_id: string;
  pattern: string;
  case_insensitive: boolean;
  severity: Severity;
  origin: "receiver" | "preset";
  preset_id: string | null;
  preset_name: string | null;
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
  channel_name: string;
  receiver_name: string;
  severity: Severity;
  content_preview: string;
  received_at: string;
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
  // "start" = ping di avvio, "end" = notifica che chiude l'esecuzione. In elenco
  // serve a non confondere un avvio con un esito.
  phase: NotificationPhase | null;
  // Dati dell'esecuzione dichiarati dal mittente: null quando la notifica non
  // arriva dal wrapper notifyhub-run.sh.
  duration_ms: number | null;
  exit_code: number | null;
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
  phase: NotificationPhase | null;
  matched_pattern: string | null;
  duration_ms: number | null;
  exit_code: number | null;
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
