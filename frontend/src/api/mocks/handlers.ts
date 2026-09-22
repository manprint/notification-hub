import { HttpResponse, http } from "msw";

// Fixture copiate dalla forma reale delle risposte dei test e2e del backend
// (fase 7/8): stessi nomi di campo, stessi valori di enum.

export const fixtureMe = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@acme.test",
  role: "owner",
  tenant_id: "22222222-2222-2222-2222-222222222222",
  tenant_name: "ACME",
};

export const fixtureTokenPair = {
  access_token: "access-token-fixture",
  refresh_token: "refresh-token-fixture",
  token_type: "bearer",
  expires_in: 900,
};

// Coerente come lo calcola il backend (api/v1/stats.py): il totale di un gruppo
// e' la somma dei suoi receiver, quindi un gruppo senza receiver sta a zero;
// total_unread e' la somma delle non lette; by_severity conta tutte le notifiche
// visibili e omette le severity che non ne hanno (qui debug).
export const fixtureStatsSummary = {
  total_unread: 5,
  by_severity: { critical: 1, error: 2, warning: 1, info: 6 } as Record<string, number>,
  by_group: [
    {
      group_id: "g1",
      group_name: "Server Produzione",
      total: 10,
      unread_count: 5,
      receivers: [
        {
          receiver_id: "r1",
          receiver_name: "Backup notturno",
          status: "active",
          total: 10,
          unread_count: 5,
        },
        {
          receiver_id: "r9",
          receiver_name: "Job mai partito",
          status: "disabled",
          total: 0,
          unread_count: 0,
        },
      ],
    },
    // Nessun receiver (come in fixtureGroups): niente notifiche. Il vecchio
    // `total: 4` con `receivers: []` era impossibile.
    { group_id: "g2", group_name: "Backup", total: 0, unread_count: 0, receivers: [] },
  ],
  // Non piu' delle notifiche totali (10).
  notifications_last_24h: 4,
  // Le consegne morte di fixtureDeliveries.
  deliveries_dead: 1,
};

export const fixtureGroups = [
  {
    id: "g1",
    name: "Server Produzione",
    description: "Ambiente di produzione",
    receiver_count: 1,
    notification_count: 5,
    unread_count: 2,
  },
  {
    id: "g2",
    name: "Backup",
    description: null,
    receiver_count: 0,
    notification_count: 0,
    unread_count: 0,
  },
];

export const fixtureGroupDetail = { ...fixtureGroups[0], receiver_count: 1 };

export const fixtureNotificationsPage1 = {
  notifications: [
    {
      id: "n1",
      receiver_id: "r1",
      content_preview: "Backup FALLITO: disco pieno su /var",
      content_size: 40,
      content_normalized: false,
      storage_backend: "inline",
      severity: "error",
      severity_source: "rule",
      phase: "end",
      duration_ms: 750_123,
      exit_code: 1,
      status: "unread",
      verified: true,
      read_by_email: null,
      read_at: null,
      verified_by_email: "mario@acme.test",
      verified_at: "2026-08-01T03:10:00Z",
      received_at: "2026-08-01T03:00:00Z",
    },
    {
      id: "n2",
      receiver_id: "r1",
      content_preview: "Tutto ok",
      content_size: 8,
      content_normalized: true,
      storage_backend: "inline",
      severity: "info",
      severity_source: "receiver_default",
      phase: null,
      duration_ms: null,
      exit_code: null,
      status: "read",
      verified: false,
      read_by_email: "owner@acme.test",
      read_at: "2026-08-01T02:05:00Z",
      verified_by_email: null,
      verified_at: null,
      received_at: "2026-08-01T02:00:00Z",
    },
  ],
  next_cursor: "cursor-page-2",
  // Non lette di tutto il tenant, indipendenti dai filtri (come nel backend).
  unread_count: 5,
};

export const fixtureNotificationsPage2 = {
  notifications: [
    {
      id: "n3",
      receiver_id: "r1",
      content_preview: "Terza notifica",
      content_size: 14,
      content_normalized: false,
      storage_backend: "inline",
      severity: "warning",
      severity_source: "receiver_default",
      phase: null,
      duration_ms: null,
      exit_code: null,
      status: "unread",
      verified: false,
      read_by_email: null,
      read_at: null,
      verified_by_email: null,
      verified_at: null,
      received_at: "2026-08-01T01:00:00Z",
    },
  ],
  next_cursor: null,
  unread_count: 5,
};

export const fixtureNotificationDetailInline = {
  id: "n1",
  receiver_id: "r1",
  content: "Backup FALLITO: disco pieno su /var",
  content_url: null,
  content_preview: "Backup FALLITO: disco pieno su /var",
  content_size: 40,
  content_normalized: false,
  severity: "error",
  severity_source: "rule",
  phase: "end",
  matched_pattern: "FALL(ITO|IMENT)|ERROR|CRITICAL",
  duration_ms: 750_123,
  exit_code: 1,
  status: "unread",
  verified: true,
  read_by_email: null,
  read_at: null,
  verified_by_email: "mario@acme.test",
  verified_at: "2026-08-01T03:10:00Z",
  received_at: "2026-08-01T03:00:00Z",
  source_ip: "203.0.113.5",
};

export const fixtureNotificationDetailObject = {
  id: "n4",
  receiver_id: "r1",
  content: null,
  content_url: "/api/v1/notifications/n4/content",
  // Per un payload su object storage content_preview e' pieno: i primi 4096
  // caratteri del corpo.
  content_preview: "y".repeat(4096),
  content_size: 2_097_152,
  content_normalized: false,
  severity: "critical",
  // Header X-Severity: nell'enum del backend (db/types.py) e' "explicit". Il
  // vecchio "header" non esiste e cadeva nel ripiego dell'etichetta.
  severity_source: "explicit",
  phase: null,
  matched_pattern: null,
  duration_ms: null,
  exit_code: null,
  status: "unread",
  verified: false,
  read_by_email: null,
  read_at: null,
  verified_by_email: null,
  verified_at: null,
  received_at: "2026-08-01T04:00:00Z",
  source_ip: "203.0.113.5",
};

export const fixtureReceiver = {
  id: "r1",
  group_id: "g1",
  slug: "maritime-backup-notturno-Kj8mQ2xN7vB4pR9wLs3tYc",
  ingest_url: "https://notifyhub.example.com/ingest/maritime-backup-notturno-Kj8mQ2xN7vB4pR9wLs3tYc",
  name: "Backup notturno",
  status: "active",
  ingestion_module: "http_raw",
  default_severity: "info",
  exit_code_severity: "critical",
  duration_threshold_seconds: 600,
  duration_severity: "error",
  max_body_bytes: 1_048_576,
  rate_limit_per_min: 60,
  rejected_last_24h: 0,
  // Sorveglianza dell'attesa attiva: un invio al giorno, mezz'ora di tolleranza.
  expected_every_seconds: 86_400,
  expected_cron: null,
  expected_timezone: null,
  expected_grace_seconds: 1_800,
  missing_severity: "critical",
  last_notification_at: "2026-08-04T03:00:12Z",
  last_start_at: "2026-08-04T03:00:01Z",
  missing_alerted_at: null,
  expected_since: "2026-07-01T00:00:00Z",
  expected_deadline_at: "2026-08-05T03:30:12Z",
  expected_late: false,
};

/** Lo script come lo serve il backend: le due righe compilate del blocco
 * "configurazione" bastano a verificare cosa arriva all'utente. */
export const fixtureWrapperScript = `#!/bin/bash
URL="\${NOTIFYHUB_URL:-${fixtureReceiver.ingest_url.replace("/ingest/" + fixtureReceiver.slug, "")}}"
SLUG="\${NOTIFYHUB_SLUG:-${fixtureReceiver.slug}}"
`;

export const fixtureSeverityReplay = {
  items: [
    {
      notification_id: "n1",
      received_at: "2026-08-01T03:00:00Z",
      content_preview: "Backup FALLITO: disco pieno su /var",
      truncated: false,
      stored_severity: "info",
      stored_source: "receiver_default",
      replayed_severity: "error",
      replayed_source: "rule",
      matched_rule_id: "sr1",
      matched_pattern: "FALL(ITO|IMENT)|ERROR|CRITICAL",
      matched_preset_name: null,
      changed: true,
    },
    {
      notification_id: "n2",
      received_at: "2026-08-01T02:00:00Z",
      content_preview: "Tutto ok",
      truncated: false,
      stored_severity: "info",
      stored_source: "receiver_default",
      replayed_severity: "info",
      replayed_source: "receiver_default",
      matched_rule_id: null,
      matched_pattern: null,
      matched_preset_name: null,
      changed: false,
    },
  ],
  changed_count: 1,
};

export const fixturePresets = [
  {
    id: "p1",
    builtin_key: "bash-generic",
    name: "Bash generico",
    description: "Errori comuni di shell e coreutils.",
    rules_count: 2,
    receivers_count: 3,
  },
  {
    id: "p2",
    builtin_key: null,
    name: "Backup interni",
    description: "Regole nostre.",
    rules_count: 1,
    receivers_count: 0,
  },
];

export const fixturePresetDetail = {
  ...fixturePresets[0],
  rules: [
    {
      id: "pr1",
      preset_id: "p1",
      priority: 10,
      pattern: "No space left on device",
      case_insensitive: true,
      severity: "critical",
      enabled: true,
    },
    {
      id: "pr2",
      preset_id: "p1",
      priority: 20,
      pattern: "Permission denied",
      case_insensitive: true,
      severity: "error",
      enabled: false,
    },
  ],
};

export const fixturePresetCatalog = [
  {
    key: "bash-generic",
    name: "Bash generico",
    description: "Errori comuni di shell e coreutils.",
    rules_count: 14,
    installed: true,
  },
  {
    key: "rclone",
    name: "rclone",
    description: "Sincronizzazioni con rclone.",
    rules_count: 12,
    installed: false,
  },
];

export const fixtureReceiverPresets = [
  {
    preset_id: "p1",
    name: "Bash generico",
    description: "Errori comuni di shell e coreutils.",
    builtin_key: "bash-generic",
    position: 0,
    rules_count: 2,
  },
];

export const fixtureSeverityChain = [
  {
    position: 1,
    rule_id: "sr1",
    pattern: "FALL(ITO|IMENT)|ERROR|CRITICAL",
    case_insensitive: true,
    severity: "error",
    origin: "receiver",
    preset_id: null,
    preset_name: null,
  },
  {
    position: 2,
    rule_id: "pr1",
    pattern: "No space left on device",
    case_insensitive: true,
    severity: "critical",
    origin: "preset",
    preset_id: "p1",
    preset_name: "Bash generico",
  },
];

export const fixtureSeverityRules = [
  {
    id: "sr1",
    receiver_id: "r1",
    priority: 1,
    pattern: "FALL(ITO|IMENT)|ERROR|CRITICAL",
    case_insensitive: true,
    severity: "error",
    enabled: true,
  },
];

export const fixtureChannels = [
  {
    id: "c1",
    name: "Slack #ops",
    type: "slack",
    webhook_hint: "https://hooks.slack.com/***X0",
    enabled: true,
    last_success_at: "2026-08-01T03:05:00Z",
    last_error_at: null,
    last_error: null,
  },
];

export const fixtureDeliveries = [
  {
    id: "d1",
    notification_id: "n1",
    channel_id: "c1",
    channel_name: "Slack #ops",
    receiver_name: "Backup notturno",
    severity: "error",
    content_preview: "Backup FALLITO: disco pieno su /var",
    received_at: "2026-08-01T03:00:00Z",
    status: "dead",
    attempts: 5,
    next_attempt_at: "2026-08-01T05:00:00Z",
    locked_at: null,
    response_code: 503,
    last_error: "connect timeout",
    sent_at: null,
  },
  {
    id: "d2",
    notification_id: "n2",
    channel_id: "c1",
    channel_name: "Slack #ops",
    receiver_name: "Backup notturno",
    severity: "info",
    content_preview: "Tutto ok",
    received_at: "2026-08-01T02:00:00Z",
    status: "sent",
    attempts: 0,
    next_attempt_at: "2026-08-01T02:00:00Z",
    locked_at: null,
    response_code: 200,
    last_error: null,
    sent_at: "2026-08-01T02:00:01Z",
  },
  {
    id: "d3",
    notification_id: "n3",
    channel_id: "c1",
    channel_name: "Slack #ops",
    receiver_name: "Backup notturno",
    severity: "warning",
    content_preview: "Terza notifica",
    received_at: "2026-08-01T01:00:00Z",
    status: "failed",
    attempts: 2,
    next_attempt_at: "2026-08-01T01:04:00Z",
    locked_at: null,
    response_code: 500,
    last_error: "HTTP 500",
    sent_at: null,
  },
];

export const fixtureUsers = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    email: "owner@acme.test",
    role: "owner",
    status: "active",
    last_login_at: "2026-08-01T03:00:00Z",
    group_ids: [],
  },
  {
    id: "33333333-3333-3333-3333-333333333333",
    email: "member@acme.test",
    role: "member",
    status: "active",
    last_login_at: null,
    group_ids: [],
  },
];

export const fixtureTenant = {
  id: "22222222-2222-2222-2222-222222222222",
  name: "ACME",
  slug: "acme-1234abcd",
  max_body_bytes: 1_048_576,
  max_notifications_per_day: null,
  max_storage_bytes: null,
  retention_days: 90,
  audit_retention_days: 365,
  status: "active",
};

export const fixtureAuditEvents = [
  {
    id: "ae1",
    occurred_at: "2026-09-15T10:00:00Z",
    actor_user_id: "u2",
    actor_email: "mario@acme.test",
    actor_role: "member",
    action: "notification.marked_verified",
    resource_type: "notification",
    resource_id: "n1",
    resource_label: "Backup notturno fallito",
    group_id: "g1",
    group_name: "Server Produzione",
    receiver_id: "r1",
    receiver_name: "Backup notturno",
    outcome: "success",
    ip: "10.0.0.7",
    user_agent: "Mozilla/5.0",
    request_id: "req-1",
    changes: { verified: { before: false, after: true } },
    context: null,
  },
  {
    id: "ae2",
    occurred_at: "2026-09-15T09:30:00Z",
    actor_user_id: "u1",
    actor_email: "owner@acme.test",
    actor_role: "owner",
    action: "notification.bulk_marked_read",
    resource_type: "notification",
    resource_id: null,
    resource_label: null,
    group_id: "g1",
    group_name: "Server Produzione",
    receiver_id: "r1",
    receiver_name: "Backup notturno",
    outcome: "success",
    ip: "10.0.0.1",
    user_agent: "Mozilla/5.0",
    request_id: "req-2",
    changes: null,
    context: { count: 12, notification_ids: ["n1", "n2"], filters: { receiver_id: "r1" } },
  },
];

export const fixtureDeleteImpact = {
  receivers: 3,
  notifications: 128,
  deliveries: 260,
};

export const fixtureTestSeverityRule = {
  severity: "error",
  source: "rule",
  matched_rule_id: "sr1",
  matched_pattern: "FALL(ITO|IMENT)|ERROR|CRITICAL",
};

export const fixtureInvitations: Array<{
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
}> = [];

// --- filtri e paginazione come nel backend ------------------------------------
// Un mock che ignora i query param fa passare qualunque richiesta sbagliata: un
// filtro che non arriva, una data nel formato sbagliato, un cursore perso. Qui
// si rispettano almeno i parametri principali di ogni lista.

/** Receiver -> gruppo, per il filtro `group_id` delle notifiche. */
const RECEIVER_GROUP: Record<string, string> = { r1: "g1", r9: "g1" };

/** Ordine dell'enum `severity` in Postgres: `severity_min` e' un >=. */
const SEVERITY_RANK: Record<string, number> = {
  debug: 0,
  info: 1,
  warning: 2,
  error: 3,
  critical: 4,
};

function problem(status: number, detail: string) {
  const title = status === 422 ? "Validation Error" : "Error";
  return HttpResponse.json(
    { type: "/problems/validation-error", title, status, detail },
    { status },
  );
}

/** Un datetime di query string come lo leggerebbe FastAPI: `undefined` se il
 *  parametro manca, `null` se non si interpreta (il backend risponde 422). */
function parseInstant(params: URLSearchParams, key: string): number | undefined | null {
  const raw = params.get(key);
  if (raw === null || raw === "") return undefined;
  const time = new Date(raw).getTime();
  return Number.isNaN(time) ? null : time;
}

function inRange(value: string, from: number | undefined, to: number | undefined): boolean {
  const time = new Date(value).getTime();
  return (from === undefined || time >= from) && (to === undefined || time <= to);
}

/** Pagina a cursore opaco su una lista gia' filtrata e ordinata. Il cursore e'
 *  la posizione codificata: il client lo deve ripassare cosi' com'e'. */
function paginate<T>(
  rows: T[],
  params: URLSearchParams,
  defaultLimit: number,
  maxLimit: number,
): { page: T[]; next_cursor: string | null } | null {
  const limit = Number(params.get("limit") ?? defaultLimit);
  if (!Number.isInteger(limit) || limit < 1 || limit > maxLimit) return null;
  const cursor = params.get("cursor");
  let offset = 0;
  if (cursor !== null) {
    const match = /^offset-(\d+)$/.exec(cursor);
    if (!match) return null;
    offset = Number(match[1]);
  }
  const page = rows.slice(offset, offset + limit);
  const next = offset + limit;
  return { page, next_cursor: next < rows.length ? `offset-${next}` : null };
}

interface MockNotification {
  receiver_id: string;
  content_preview: string;
  severity: string;
  severity_source: string;
  status: string;
  verified: boolean;
  received_at: string;
}

function matchesNotification(n: MockNotification, params: URLSearchParams): boolean {
  const groupId = params.get("group_id");
  const receiverId = params.get("receiver_id");
  const status = params.get("status");
  const verified = params.get("verified");
  const severityMin = params.get("severity_min");
  const source = params.get("source");
  const q = params.get("q");
  const from = parseInstant(params, "from") ?? undefined;
  const to = parseInstant(params, "to") ?? undefined;
  return (
    (!groupId || RECEIVER_GROUP[n.receiver_id] === groupId) &&
    (!receiverId || n.receiver_id === receiverId) &&
    (!status || n.status === status) &&
    (verified === null || String(n.verified) === verified) &&
    (!severityMin || SEVERITY_RANK[n.severity] >= SEVERITY_RANK[severityMin]) &&
    (!source || n.severity_source === source) &&
    (!q || n.content_preview.toLowerCase().includes(q.toLowerCase())) &&
    inRange(n.received_at, from, to)
  );
}

type MockAuditEvent = (typeof fixtureAuditEvents)[number];

const NOTIFICATION_STATUS_ACTIONS = new Set([
  "notification.marked_read",
  "notification.marked_unread",
  "notification.marked_verified",
  "notification.marked_unverified",
  "notification.bulk_marked_read",
]);

/** I filtri dell'audit come in backend/app/api/v1/audit.py (`_base_query`):
 *  `from`/`to` confrontati come istanti, estremi inclusi. Esportata per i test
 *  che servono eventi propri con la stessa semantica. `null` = parametri che il
 *  backend rifiuterebbe con 422. */
export function filterAuditEvents<T extends MockAuditEvent>(
  events: T[],
  params: URLSearchParams,
  notificationStatusOnly: boolean,
): T[] | null {
  const from = parseInstant(params, "from");
  const to = parseInstant(params, "to");
  if (from === null || to === null) return null;
  const notificationId = params.get("notification_id");
  const exact: Array<keyof MockAuditEvent> = [
    "actor_user_id",
    "action",
    "resource_type",
    "resource_id",
    "outcome",
  ];
  return events.filter((event) => {
    if (notificationStatusOnly && !NOTIFICATION_STATUS_ACTIONS.has(event.action)) return false;
    for (const key of exact) {
      const wanted = params.get(key);
      if (wanted && event[key] !== wanted) return false;
    }
    if (notificationId) {
      const ids = event.context?.notification_ids ?? [];
      if (event.resource_id !== notificationId && !ids.includes(notificationId)) return false;
    }
    return inRange(event.occurred_at, from, to);
  });
}

function auditList(request: Request, notificationStatusOnly: boolean) {
  const params = new URL(request.url).searchParams;
  const events = filterAuditEvents(fixtureAuditEvents, params, notificationStatusOnly);
  if (events === null) return problem(422, "Invalid datetime.");
  const result = paginate(events, params, 50, 200);
  if (result === null) return problem(422, "Invalid cursor or limit.");
  return HttpResponse.json({ events: result.page, next_cursor: result.next_cursor });
}

const AUDIT_EXPORT_COLUMNS = [
  "occurred_at",
  "actor_email",
  "actor_role",
  "action",
  "resource_type",
  "resource_id",
  "resource_label",
  "group_name",
  "receiver_name",
  "outcome",
  "ip",
  "request_id",
  "changes",
  "context",
] as const;

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export const handlers = [
  http.get("/api/v1/auth/me", () => HttpResponse.json(fixtureMe)),
  http.post("/api/v1/auth/login", () => HttpResponse.json(fixtureTokenPair)),
  http.post("/api/v1/auth/refresh", () => HttpResponse.json(fixtureTokenPair)),
  http.get("/api/v1/stats/summary", () => HttpResponse.json(fixtureStatsSummary)),
  http.get("/api/v1/groups", () => HttpResponse.json(fixtureGroups)),
  http.get("/api/v1/groups/:groupId", () => HttpResponse.json(fixtureGroupDetail)),
  http.get("/api/v1/groups/:groupId/receivers", () => HttpResponse.json([fixtureReceiver])),
  http.get("/api/v1/groups/:groupId/delete-impact", () => HttpResponse.json(fixtureDeleteImpact)),
  http.get("/api/v1/groups/:groupId/channels", () => HttpResponse.json([])),
  http.get("/api/v1/notifications", ({ request }) => {
    const params = new URL(request.url).searchParams;
    if (parseInstant(params, "from") === null || parseInstant(params, "to") === null) {
      return problem(422, "Invalid datetime.");
    }
    const cursor = params.get("cursor");
    if (cursor !== null && cursor !== fixtureNotificationsPage1.next_cursor) {
      return problem(422, "Invalid cursor.");
    }
    const limit = Number(params.get("limit") ?? 50);
    // Due pagine fisse, filtrate: la seconda esiste solo se i filtri vi
    // lasciano qualcosa, come farebbe il cursore del backend.
    const page = cursor ? fixtureNotificationsPage2 : fixtureNotificationsPage1;
    const matching = page.notifications.filter((n) => matchesNotification(n, params));
    const hasNext =
      !cursor && fixtureNotificationsPage2.notifications.some((n) => matchesNotification(n, params));
    return HttpResponse.json({
      ...page,
      notifications: matching.slice(0, limit),
      next_cursor: hasNext ? page.next_cursor : null,
    });
  }),
  http.get("/api/v1/notifications/n1", () => HttpResponse.json(fixtureNotificationDetailInline)),
  http.get("/api/v1/notifications/n4", () => HttpResponse.json(fixtureNotificationDetailObject)),
  http.patch("/api/v1/notifications/:id", async ({ request, params }) => {
    const body = (await request.json()) as { status?: string; verified?: boolean };
    const base =
      String(params.id) === "n4"
        ? { ...fixtureNotificationDetailObject, ...body }
        : { ...fixtureNotificationDetailInline, ...body };
    return HttpResponse.json(base);
  }),
  http.post("/api/v1/notifications/bulk-read", () => HttpResponse.json({ marked_read: 0 })),
  http.get("/api/v1/receivers", () => HttpResponse.json([fixtureReceiver])),
  http.get("/api/v1/receivers/r1", () => HttpResponse.json(fixtureReceiver)),
  http.get("/api/v1/receivers/r1/severity-rules", () => HttpResponse.json(fixtureSeverityRules)),
  http.get("/api/v1/receivers/r1/severity-rules/replay", () =>
    HttpResponse.json(fixtureSeverityReplay),
  ),
  http.post("/api/v1/receivers/r1/test-severity", () => HttpResponse.json(fixtureTestSeverityRule)),
  http.get("/api/v1/channels", () => HttpResponse.json(fixtureChannels)),
  http.get("/api/v1/deliveries", ({ request }) => {
    // Contratto C2: pagina a cursore, ordinata per ricezione della notifica.
    const params = new URL(request.url).searchParams;
    const status = params.get("status");
    const channelId = params.get("channel_id");
    const rows = fixtureDeliveries
      .filter((d) => (!status || d.status === status) && (!channelId || d.channel_id === channelId))
      .sort((a, b) => b.received_at.localeCompare(a.received_at));
    const result = paginate(rows, params, 100, 500);
    if (result === null) return problem(422, "Invalid cursor or limit.");
    return HttpResponse.json({ deliveries: result.page, next_cursor: result.next_cursor });
  }),
  http.get("/api/v1/users", () => HttpResponse.json(fixtureUsers)),
  http.get("/api/v1/tenant", () => HttpResponse.json(fixtureTenant)),
  http.get("/api/v1/audit/events", ({ request }) => auditList(request, false)),
  http.get("/api/v1/audit/notification-status", ({ request }) => auditList(request, true)),
  http.get("/api/v1/audit/export", ({ request }) => {
    const params = new URL(request.url).searchParams;
    const statusOnly = params.get("notification_status_only") === "true";
    const events = filterAuditEvents(fixtureAuditEvents, params, statusOnly);
    if (events === null) return problem(422, "Invalid datetime.");
    const format = params.get("format") ?? "csv";
    if (format === "json") {
      return HttpResponse.json(events, {
        headers: { "Content-Disposition": 'attachment; filename="audit-20260915-100000.json"' },
      });
    }
    // Come il backend: UTF-8 senza BOM, una riga d'intestazione.
    const lines = [
      AUDIT_EXPORT_COLUMNS.join(","),
      ...events.map((event) =>
        AUDIT_EXPORT_COLUMNS.map((column) => csvCell(event[column])).join(","),
      ),
    ];
    return HttpResponse.text(`${lines.join("\r\n")}\r\n`, {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="audit-20260915-100000.csv"',
      },
    });
  }),
  http.get("/api/v1/invitations", () => HttpResponse.json(fixtureInvitations)),
  http.get("/api/v1/receivers/:receiverId/channels", () => HttpResponse.json([])),
  http.get("/api/v1/severity-presets", () => HttpResponse.json(fixturePresets)),
  http.get("/api/v1/severity-presets/catalog", () => HttpResponse.json(fixturePresetCatalog)),
  http.get("/api/v1/severity-presets/p1", () => HttpResponse.json(fixturePresetDetail)),
  http.get("/api/v1/receivers/:receiverId/presets", () =>
    HttpResponse.json(fixtureReceiverPresets),
  ),
  http.get("/api/v1/receivers/:receiverId/severity-chain", () =>
    HttpResponse.json(fixtureSeverityChain),
  ),
  http.get("/api/v1/receivers/:receiverId/wrapper-script", () =>
    HttpResponse.text(fixtureWrapperScript, {
      headers: {
        "Content-Type": "text/x-shellscript; charset=utf-8",
        "Content-Disposition": 'attachment; filename="notifyhub-run-backup-notturno.sh"',
      },
    }),
  ),
];
