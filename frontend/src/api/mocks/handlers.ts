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

export const fixtureStatsSummary = {
  total_unread: 7,
  by_severity: { critical: 1, error: 2, warning: 1, info: 3, debug: 0 },
  by_group: [
    { group_id: "g1", group_name: "Server Produzione", total: 10, unread_count: 5 },
    { group_id: "g2", group_name: "Backup", total: 4, unread_count: 2 },
  ],
  notifications_last_24h: 12,
  deliveries_dead: 3,
};

export const fixtureGroups = [
  { id: "g1", name: "Server Produzione", description: "Ambiente di produzione" },
  { id: "g2", name: "Backup", description: null },
];

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
      status: "unread",
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
      status: "read",
      received_at: "2026-08-01T02:00:00Z",
    },
  ],
  next_cursor: "cursor-page-2",
  unread_count: 7,
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
      status: "unread",
      received_at: "2026-08-01T01:00:00Z",
    },
  ],
  next_cursor: null,
  unread_count: 7,
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
  matched_pattern: "FALL(ITO|IMENT)|ERROR|CRITICAL",
  status: "unread",
  received_at: "2026-08-01T03:00:00Z",
  source_ip: "203.0.113.5",
};

export const fixtureNotificationDetailObject = {
  id: "n4",
  receiver_id: "r1",
  content: null,
  content_url: "/api/v1/notifications/n4/content",
  content_preview: "y".repeat(500),
  content_size: 2_097_152,
  content_normalized: false,
  severity: "critical",
  severity_source: "header",
  matched_pattern: null,
  status: "unread",
  received_at: "2026-08-01T04:00:00Z",
  source_ip: "203.0.113.5",
};

export const fixtureReceiver = {
  id: "r1",
  group_id: "g1",
  slug: "Kj8mQ2xN7vB4pR9wLs3tYc",
  name: "Backup notturno",
  status: "active",
  ingestion_module: "http_raw",
  default_severity: "info",
  max_body_bytes: 1_048_576,
  rate_limit_per_min: 60,
  rejected_last_24h: 0,
};

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
    status: "sent",
    attempts: 0,
    next_attempt_at: "2026-08-01T02:00:00Z",
    locked_at: null,
    response_code: 200,
    last_error: null,
    sent_at: "2026-08-01T02:00:01Z",
  },
];

export const fixtureUsers = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    email: "owner@acme.test",
    role: "owner",
    status: "active",
    last_login_at: "2026-08-01T03:00:00Z",
  },
  {
    id: "33333333-3333-3333-3333-333333333333",
    email: "member@acme.test",
    role: "member",
    status: "active",
    last_login_at: null,
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
  status: "active",
};

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

export const handlers = [
  http.get("/api/v1/auth/me", () => HttpResponse.json(fixtureMe)),
  http.post("/api/v1/auth/login", () => HttpResponse.json(fixtureTokenPair)),
  http.post("/api/v1/auth/refresh", () => HttpResponse.json(fixtureTokenPair)),
  http.get("/api/v1/stats/summary", () => HttpResponse.json(fixtureStatsSummary)),
  http.get("/api/v1/groups", () => HttpResponse.json(fixtureGroups)),
  http.get("/api/v1/groups/:groupId/receivers", () => HttpResponse.json([fixtureReceiver])),
  http.get("/api/v1/groups/:groupId/delete-impact", () => HttpResponse.json(fixtureDeleteImpact)),
  http.get("/api/v1/groups/:groupId/channels", () => HttpResponse.json([])),
  http.get("/api/v1/notifications", ({ request }) => {
    const url = new URL(request.url);
    const cursor = url.searchParams.get("cursor");
    return HttpResponse.json(cursor ? fixtureNotificationsPage2 : fixtureNotificationsPage1);
  }),
  http.get("/api/v1/notifications/n1", () => HttpResponse.json(fixtureNotificationDetailInline)),
  http.get("/api/v1/notifications/n4", () => HttpResponse.json(fixtureNotificationDetailObject)),
  http.get("/api/v1/receivers/r1", () => HttpResponse.json(fixtureReceiver)),
  http.get("/api/v1/receivers/r1/severity-rules", () => HttpResponse.json(fixtureSeverityRules)),
  http.post("/api/v1/receivers/r1/test-severity", () => HttpResponse.json(fixtureTestSeverityRule)),
  http.get("/api/v1/channels", () => HttpResponse.json(fixtureChannels)),
  http.get("/api/v1/deliveries", () => HttpResponse.json(fixtureDeliveries)),
  http.get("/api/v1/users", () => HttpResponse.json(fixtureUsers)),
  http.get("/api/v1/tenant", () => HttpResponse.json(fixtureTenant)),
];
