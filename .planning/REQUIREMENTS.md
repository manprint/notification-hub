# Requirements: NotifyHub Notification Operations Increment

**Defined:** 2026-08-04  
**Core Value:** Operators can reliably identify, filter, acknowledge, and verify notification state without losing delivery or tenant isolation guarantees.

## v1 Requirements

### Notification State

- [ ] **NOTIF-01**: A user with `member`, `admin`, or `owner` role can toggle a notification from read to unread and from unread to read.
- [ ] **NOTIF-02**: A user with `member`, `admin`, or `owner` role can toggle a notification from unverified to verified and from verified to unverified.
- [ ] **NOTIF-03**: Read/unread and verified/unverified remain independent, so changing one state never changes the other.
- [ ] **NOTIF-04**: A viewer can see notification states but cannot mutate read or verified state through the API.

### Notification Filters and UI

- [ ] **NOTIF-05**: The notification list can filter server-side by read/unread state while retaining existing group, severity, source, search, and pagination behavior.
- [ ] **NOTIF-06**: The notification list can filter server-side by verified/unverified state and combine that filter with the read/unread filter and existing filters.
- [ ] **NOTIF-07**: The notification list and detail view display both state badges, with direct clickable actions and accessible labels for the allowed transitions.
- [ ] **NOTIF-08**: Existing unread counts, bulk-read behavior, and notification query invalidation remain correct after adding verification state.

### Receiver Cron Feedback

- [ ] **CRON-01**: The receiver editor validates a five-field cron expression as it changes and shows an actionable error in red when the expression is invalid.
- [ ] **CRON-02**: The receiver editor blocks saving while the cron expression is invalid, and the backend rejects invalid cron expressions regardless of client behavior.
- [ ] **CRON-03**: For every valid cron expression and selected IANA time zone, the receiver editor shows the next three scheduled execution times in that time zone.
- [ ] **CRON-04**: The next-three preview refreshes after each valid cron or time-zone change and handles DST/time-zone behavior consistently with missing-job surveillance.

### Quality and Regression Safety

- [ ] **QUAL-01**: Automated backend and frontend tests cover all notification state combinations, role authorization, combined filters, cron validation, preview calculation, time zones, and invalid-save blocking.

## v2 Requirements

None identified for this increment.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automatic verification after delivery | Operational verification is an explicit human state, independent from transport success. |
| New ingestion or outbound integrations | This increment improves notification triage and receiver schedule feedback only. |
| Mobile/push notification clients | No requirement in the requested scope. |
| Changing cron syntax or surveillance semantics | Existing five-field cron and missing-job behavior remain the compatibility contract. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NOTIF-01 | Phase 1 | Pending |
| NOTIF-02 | Phase 2 | Pending |
| NOTIF-03 | Phase 1 | Pending |
| NOTIF-04 | Phase 2 | Pending |
| NOTIF-05 | Phase 3 | Pending |
| NOTIF-06 | Phase 3 | Pending |
| NOTIF-07 | Phase 4 | Pending |
| NOTIF-08 | Phase 4 | Pending |
| CRON-01 | Phase 5 | Pending |
| CRON-02 | Phase 6 | Pending |
| CRON-03 | Phase 7 | Pending |
| CRON-04 | Phase 7 | Pending |
| QUAL-01 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0

---
*Requirements defined: 2026-08-04*
*Last updated: 2026-08-04 after initialization*
