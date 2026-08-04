# Project Research Summary

**Project:** NotifyHub
**Domain:** Multi-tenant notification operations dashboard
**Researched:** 2026-08-04
**Confidence:** HIGH

## Executive Summary

This is a focused brownfield increment over an established FastAPI/PostgreSQL and React dashboard. The safest approach is to extend existing notification contracts with an independent verification dimension and to keep cron preview logic server-authoritative using the existing `croniter` and IANA time-zone implementation.

The main risks are coupling read and verified transitions, exposing mutation to viewers, and allowing frontend cron semantics to diverge from worker surveillance. A small number of vertical phases with backend/API tests first and UI integration second will address those risks directly.

## Key Findings

### Recommended Stack

- Existing FastAPI, SQLAlchemy/Alembic, PostgreSQL, React/TypeScript, and React Query — preserve architecture and contracts.
- Existing `croniter` plus Python `zoneinfo` — authoritative five-field, DST-aware schedule preview.

### Expected Features

**Must have:** reversible read state, independent verification, combined server-side filters, live cron validation, and next-three preview.

**Should have:** direct badge actions and explicit time-zone display.

**Defer:** automatic verification and new ingestion/outbound channels.

### Architecture Approach

Extend the current model, API, and SPA without introducing a new service. Keep tenant/RLS and role enforcement at the API boundary; keep unsaved cron preview separate from persistence while reusing surveillance calculation logic.

### Critical Pitfalls

1. Keep read and verification independent with a four-combination test matrix.
2. Enforce viewer denial on the backend, not only in the UI.
3. Use one server-side cron/time-zone authority and block invalid saves.

## Implications for Roadmap

### Phase 1: Notification state and filters

**Rationale:** State persistence, authorization, and query contracts are the foundation for every notification UI action.
**Delivers:** Independent verification, reversible read state, list/detail badges, and combined filters with tests.
**Avoids:** Coupled states and client-only authorization.

### Phase 2: Cron editor feedback

**Rationale:** Receiver preview depends on the existing schedule contract but can be delivered independently after state work.
**Delivers:** Live validation, blocked invalid saves, and next three time-zone-aware occurrences.
**Avoids:** Browser/backend disagreement and DST ambiguity.

### Phase Ordering Rationale

- Backend contracts and migrations precede UI actions.
- Each phase is a vertical slice with targeted tests and can be planned into fine-grained sequential plans.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against repository dependencies and code |
| Features | HIGH | Directly specified by user and existing UI |
| Architecture | HIGH | Existing boundaries are clear |
| Pitfalls | HIGH | Derived from existing tests and security model |

**Overall confidence:** HIGH

### Gaps to Address

- Decide whether preview is a dedicated endpoint or an extension of the receiver response during phase planning.
- Confirm exact display format for localized timestamps while preserving unambiguous zone information.

## Sources

- Existing repository code and tests (primary)
- `.planning/PROJECT.md` and `.planning/codebase/` (primary)

---
*Research completed: 2026-08-04*
*Ready for roadmap: yes*
