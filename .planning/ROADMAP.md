# Roadmap: NotifyHub Notification Operations Increment

## Overview

This milestone extends the existing NotifyHub dashboard with trustworthy operator state and schedule feedback. The roadmap moves from durable notification state and authorization through server-side filters and UI actions, then delivers a server-authoritative cron preview with invalid-save protection and a final cross-layer verification pass.

## Phases

- [ ] **Phase 1: Notification State Model** - Persist an independent verified state alongside read/unread without weakening tenant isolation.
- [ ] **Phase 2: State Mutation API** - Expose reversible state transitions with role enforcement for member, admin, and owner.
- [ ] **Phase 3: Notification Query Filters** - Add read and verified predicates to paginated notification queries and counts.
- [ ] **Phase 4: Notification State UI** - Make both badges directly actionable in list/detail views and preserve existing unread behavior.
- [ ] **Phase 5: Cron Preview Domain** - Establish shared validation and next-three calculation contracts using the configured time zone.
- [ ] **Phase 6: Cron Preview API** - Provide an unsaved-input preview contract and enforce invalid cron rejection at persistence boundaries.
- [ ] **Phase 7: Receiver Editor Feedback** - Render live red validation, next-three execution preview, and blocked saves in the frontend.
- [ ] **Phase 8: Cross-Layer Verification** - Complete regression coverage and verify combined notification states and DST-aware cron behavior.

## Phase Details

### Phase 1: Notification State Model
**Goal**: Store verified/unverified independently from read/unread for every tenant notification.
**Depends on**: Nothing (first phase)
**Requirements**: [NOTIF-03]
**Success Criteria** (what must be TRUE):
  1. Existing notifications default to unverified during migration.
  2. The model and database represent verified state independently from read status.
  3. Tenant-scoped queries and existing unread indexes continue to function.
**Plans**: 1 plan

Plans:
- [ ] 01-01: Add notification verification persistence, migration, model/schema coverage, and migration tests.

### Phase 2: State Mutation API
**Goal**: Allow authorized operators to reverse read state and toggle verification without coupling transitions.
**Depends on**: Phase 1
**Requirements**: [NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04]
**Success Criteria** (what must be TRUE):
  1. Member, admin, and owner can toggle either state independently through the API.
  2. Viewer can read state but receives a permission error when mutating either state.
  3. Invalid state payloads and cross-tenant identifiers are rejected using existing API conventions.
**Plans**: 2 plans

Plans:
- [ ] 02-01: Extend notification patch schemas/routes and authorization for independent state transitions.
- [ ] 02-02: Add backend mutation, role, tenant-boundary, and regression tests.

### Phase 3: Notification Query Filters
**Goal**: Filter notifications server-side by both state dimensions while preserving existing pagination and counts.
**Depends on**: Phase 2
**Requirements**: [NOTIF-05, NOTIF-06]
**Success Criteria** (what must be TRUE):
  1. API consumers can request read/unread and verified/unverified filters independently.
  2. Both filters can be combined with group, severity, source, search, and cursor pagination.
  3. Returned counts and empty results reflect the active state predicates.
**Plans**: 2 plans

Plans:
- [ ] 03-01: Extend notification query schemas, SQL predicates, indexes if needed, and response typing.
- [ ] 03-02: Add backend filter-combination, pagination, count, and performance regression tests.

### Phase 4: Notification State UI
**Goal**: Make read and verified states visible and directly reversible in the notification experience.
**Depends on**: Phase 3
**Requirements**: [NOTIF-07, NOTIF-08]
**Success Criteria** (what must be TRUE):
  1. List and detail views display independent read and verified badges.
  2. Clicking either badge toggles only that state and refreshes the relevant list/detail/count data.
  3. The list exposes URL-backed filters for both state dimensions and retains existing filters.
  4. Existing bulk-read and unread-count behavior remains unchanged.
**Plans**: 3 plans

Plans:
- [ ] 04-01: Extend frontend notification types, status-pill variants, and list/detail state actions.
- [ ] 04-02: Add read/verified filter controls and query-key/URL integration.
- [ ] 04-03: Update frontend fixtures and component/page tests for all state combinations and interactions.

### Phase 5: Cron Preview Domain
**Goal**: Define a single server-side domain calculation for validation and the next three schedule occurrences.
**Depends on**: Phase 4
**Requirements**: [CRON-01, CRON-03, CRON-04]
**Success Criteria** (what must be TRUE):
  1. Valid five-field cron expressions produce exactly the next three occurrences.
  2. Occurrences are calculated in the selected IANA time zone and remain correct across DST transitions.
  3. Invalid expressions and invalid time zones produce structured domain errors consistent with existing validation.
**Plans**: 1 plan

Plans:
- [ ] 05-01: Extract or extend shared cron preview calculation and add timezone/DST/error tests.

### Phase 6: Cron Preview API
**Goal**: Expose unsaved cron preview feedback and keep receiver persistence protected by backend validation.
**Depends on**: Phase 5
**Requirements**: [CRON-02, CRON-03, CRON-04]
**Success Criteria** (what must be TRUE):
  1. The API can calculate a preview for unsaved cron and time-zone input.
  2. Invalid cron cannot be persisted even if the client bypasses UI validation.
  3. Preview responses carry enough time-zone/context information for unambiguous rendering.
**Plans**: 2 plans

Plans:
- [ ] 06-01: Add receiver preview request/response contract and route/service integration.
- [ ] 06-02: Add API tests for valid/invalid cron, timezone errors, authorization, and save rejection.

### Phase 7: Receiver Editor Feedback
**Goal**: Provide immediate, clear cron validation and next-run feedback during receiver editing.
**Depends on**: Phase 6
**Requirements**: [CRON-01, CRON-02, CRON-03, CRON-04]
**Success Criteria** (what must be TRUE):
  1. Invalid cron is marked in red with an actionable message.
  2. The save action is disabled or blocked while cron is invalid.
  3. Every valid edit of cron or time zone refreshes the next-three preview.
  4. Preview timestamps identify the selected time zone and use the existing receiver form semantics.
**Plans**: 2 plans

Plans:
- [ ] 07-01: Implement controlled cron validation, preview requests, loading/error states, and save gating.
- [ ] 07-02: Add receiver editor tests for valid edits, invalid edits, timezone changes, and preview rendering.

### Phase 8: Cross-Layer Verification
**Goal**: Demonstrate that the complete increment satisfies requirements without regressions.
**Depends on**: Phase 7
**Requirements**: [QUAL-01]
**Success Criteria** (what must be TRUE):
  1. Backend unit/integration tests cover state transitions, roles, tenant boundaries, filters, and cron/DST behavior.
  2. Frontend tests cover badge actions, combined filters, invalid-save blocking, and next-three previews.
  3. Existing formatting, lint, type, build, and relevant smoke/gate commands pass.
**Plans**: 2 plans

Plans:
- [ ] 08-01: Run Nyquist-focused cross-layer test matrix and close any coverage gaps.
- [ ] 08-02: Run project quality gates, review API/UI compatibility, and document verification evidence.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Notification State Model | 0/1 | Not started | - |
| 2. State Mutation API | 0/2 | Not started | - |
| 3. Notification Query Filters | 0/2 | Not started | - |
| 4. Notification State UI | 0/3 | Not started | - |
| 5. Cron Preview Domain | 0/1 | Not started | - |
| 6. Cron Preview API | 0/2 | Not started | - |
| 7. Receiver Editor Feedback | 0/2 | Not started | - |
| 8. Cross-Layer Verification | 0/2 | Not started | - |
