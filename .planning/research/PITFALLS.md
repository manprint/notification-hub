# Pitfalls Research

**Domain:** Notification operations dashboard and cron surveillance
**Researched:** 2026-08-04
**Confidence:** HIGH

## Critical Pitfalls

### Independent states accidentally coupled

**What goes wrong:** Marking a notification read also marks it verified, or reverting read resets verification.

**How to avoid:** Persist and patch the dimensions independently; add all four combination tests.

**Warning signs:** A single enum replaces existing status, or patch handlers accept only a generic transition.

**Phase to address:** Notification state and filters.

### Authorization gap on verification

**What goes wrong:** Viewers can mutate verification through a guessed API request even if the UI hides the button.

**How to avoid:** Enforce `member/admin/owner` authorization in the API and test viewer denial.

**Warning signs:** Permission is checked only in React.

**Phase to address:** Notification state and filters.

### Frontend/backend cron disagreement

**What goes wrong:** UI accepts a cron the surveillance worker rejects, or next-run times differ around DST.

**How to avoid:** Make backend validation and preview authoritative and reuse existing surveillance helpers.

**Warning signs:** A new JavaScript cron parser is introduced or tests use only UTC.

**Phase to address:** Cron editor feedback.

### Invalid preview can still be saved

**What goes wrong:** Red validation feedback is displayed, but stale valid form state or a race permits an invalid PATCH.

**How to avoid:** Disable save while invalid and keep backend schema validation as the final gate.

**Warning signs:** Save button depends on error text rather than canonical validation state.

**Phase to address:** Cron editor feedback.

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Badge has no clear action affordance | Operators miss that it is clickable | Use button semantics, labels/tooltips, and accessible state text |
| Filter selection lost on mutation | Triage context disappears | Keep filters in URL and invalidate/refetch in place |
| Preview timestamps omit time zone | Schedule appears ambiguous | Include configured zone and localized date/time |

## “Looks Done But Isn't” Checklist

- [ ] Read state can revert in list and detail, not only become read.
- [ ] Verification mutation is denied for viewer and remains independent of read state.
- [ ] Both filters are server-side and work with cursor pagination.
- [ ] Cron invalidity is tested for syntax, timezone, and save blocking.
- [ ] Next three executions are tested across a non-UTC zone and DST boundary.

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Coupled states | Phase 1 | Four-state transition matrix |
| Authorization gap | Phase 1 | Viewer/member/admin/owner API tests |
| Cron disagreement | Phase 2 | Shared helper and timezone/DST tests |
| Invalid save | Phase 2 | UI validation and no-PATCH test |

## Sources

- Existing tests and implementation in `backend/app/services/surveillance.py`, `backend/tests/unit/test_surveillance.py`, and frontend page tests (HIGH)
- User acceptance decisions captured during onboarding (HIGH)

---
*Pitfalls research for: brownfield notification dashboard increment*
*Researched: 2026-08-04*
