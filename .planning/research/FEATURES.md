# Feature Research

**Domain:** Notification operations dashboard
**Researched:** 2026-08-04
**Confidence:** HIGH

## Feature Landscape

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Reversible read state | Operators correct accidental acknowledgements | LOW | Must preserve current status semantics and unread counts |
| Explicit verification state | Read does not mean operationally checked | MEDIUM | Independent, role-controlled, and reversible |
| State filters | Operators need focused queues | MEDIUM | URL/query-backed filters should combine with group, severity, source, and search |
| Inline cron validation | Invalid schedules are operationally dangerous | MEDIUM | Red error, actionable message, blocked save |
| Next three cron occurrences | Operators need to verify schedule interpretation | MEDIUM | Refresh on valid edits and selected IANA time zone |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Direct badge actions | Fast triage with low interaction cost | LOW | Reuse existing status-pill visual language |
| Time-zone-aware preview | Makes DST and local schedule behavior visible | MEDIUM | Display zone and localized timestamps clearly |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Automatic verification after delivery | Seems to reduce operator work | Delivery is not human or operational verification | Keep explicit verified state |
| Client-only cron validation | Immediate feedback | Diverges from server semantics | Server-backed validation/preview |
| Four-value combined state | Fewer fields | Prevents independent transitions and complicates filters | Two boolean/state dimensions |

## Feature Dependencies

```
Notification persistence/API
    ├──> role-aware state mutation
    ├──> list/detail badges
    └──> combined read + verified filters

Receiver cron validation
    └──> time-zone-aware next-three preview
```

## MVP Definition

### Launch With (v1)

- [ ] Reversible read/unread state
- [ ] Independent verified/unverified state with authorization
- [ ] Combined list filters
- [ ] Live invalid-cron feedback and blocked save
- [ ] Next three valid cron occurrences in configured time zone

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Independent verification | HIGH | MEDIUM | P1 |
| State filters | HIGH | MEDIUM | P1 |
| Cron validation | HIGH | MEDIUM | P1 |
| Next-run preview | HIGH | MEDIUM | P1 |

## Sources

- Existing user requirements captured in `.planning/PROJECT.md` (HIGH)
- Existing notification and receiver UI/API implementation (HIGH)

---
*Feature research for: brownfield notification dashboard increment*
*Researched: 2026-08-04*
