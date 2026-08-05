# Phase 1 — Backend `receiver_count`

> **Intent:** Extend `GroupOut` with `receiver_count: int` and populate it in all
> group endpoints so the frontend table can show configured receivers per group.
> **Shippable alone?** yes — additive API field; existing frontend ignores it.
> **Preconditions:** none

Follow the repo's existing backend conventions: FastAPI routers under
`backend/app/api/v1/`, Pydantic schemas under `backend/app/schemas/`, unit tests
in `backend/tests/unit/`, e2e in `backend/tests/e2e/`. No new directories.

---

## Sub-phases

### 1.1 Add `receiver_count` to the group output contract and populate it
- **Model:** agent-2:sonnet (data-model design; **agent-1:opus review gate**)
- **Assignment:** agent-2:sonnet — implement; agent-1:opus — approve D1 schema.
- **Files:**
  - `backend/app/schemas/group.py:18-29` — `GroupOut`
  - `backend/app/api/v1/groups.py:3-5` (imports), `:43-58` (`list_groups`),
    `:62-77` (`create_group`), `:81-88` (`get_group`), `:92-106` (`update_group`)
- **Change:**
  1. `schemas/group.py` — in `GroupOut` add `receiver_count: int` after `description`.
     Keep `model_config = ConfigDict(from_attributes=True)` unchanged.
  2. `groups.py` — imports:
     - Line 4 is `from sqlalchemy import select`. Change it to `from sqlalchemy import func, select` (do not add a second `select` import).
     - After `from app.models.group import Group` (line 12) add `from app.models.receiver import Receiver` (keeps the `app.models.*` import block together).
  3. `groups.py` — add this module-level helper after `_get_group_or_404` (after line 39):
     ```python
     def _group_out(group: Group, receiver_count: int) -> GroupOut:
         return GroupOut(
             id=group.id,
             name=group.name,
             description=group.description,
             receiver_count=receiver_count,
         )

     async def _receiver_counts(
         session: AsyncSession,
         tenant_id: uuid.UUID,
         group_ids: list[uuid.UUID],
     ) -> dict[uuid.UUID, int]:
         if not group_ids:
             return {}
         result = await session.execute(
             select(Receiver.group_id, func.count())
             .where(
                 Receiver.tenant_id == tenant_id,
                 Receiver.group_id.in_(group_ids),
             )
             .group_by(Receiver.group_id)
         )
         return {group_id: count for group_id, count in result.all()}
     ```
     Follow the aggregate-count pattern at `backend/app/api/v1/presets.py:144`.
  4. `list_groups` (`:42-58`) — replace the final `return` line 58 with:
     ```python
     groups = result.scalars().all()
     counts = await _receiver_counts(
         session, uuid.UUID(claims.tid), [g.id for g in groups]
     )
     return [_group_out(g, counts.get(g.id, 0)) for g in groups]
     ```
  5. `create_group` (`:61-77`) — replace `return GroupOut.model_validate(group)` (line 77) with `return _group_out(group, 0)`.
  6. `get_group` (`:80-88`) — replace line 88 with:
     ```python
     count = await _receiver_counts(session, uuid.UUID(claims.tid), [group.id])
     return _group_out(group, count.get(group.id, 0))
     ```
  7. `update_group` (`:91-106`) — replace line 106 `return GroupOut.model_validate(group)` with:
     ```python
     count = await _receiver_counts(session, uuid.UUID(claims.tid), [group.id])
     return _group_out(group, count.get(group.id, 0))
     ```
  Do not change route paths, auth, or the delete flow.
- **Unit tests:** `test_group_out_schema` — now passes `receiver_count=0` and asserts it; `test_receiver_counts_returns_zero_for_empty` — `_receiver_counts(session, tid, []) == {}`.
- **e2e tests:** T-GRP1 — `GET /api/v1/groups` returns every group with integer `receiver_count`; group with receivers has count >= 1 (assert exact against the created receiver).
- **Done:** gates green (`make gates`) AND `tests/unit/test_groups.py::test_group_out_schema` updated with `receiver_count` AND `GET /api/v1/groups` returns `receiver_count`.

### 1.2 Backend tests for `receiver_count`
- **Model:** agent-2:sonnet
- **Assignment:** agent-2:sonnet — write tests; update the existing one.
- **Files:**
  - `backend/tests/unit/test_groups.py` (schema test at line ~30)
  - `backend/tests/e2e/test_user_group_memberships.py` (has group + receiver fixtures; add count assertions here) — or create `backend/tests/e2e/test_groups_receiver_count.py` if the memberships file does not cover the happy path; follow existing e2e test conventions in `backend/tests/e2e/`.
- **Change:**
  1. Update `test_group_out_schema` (unit) to construct `GroupOut(..., receiver_count=0)` and assert `group_out.receiver_count == 0`.
  2. Add unit test `test_group_out_schema_receiver_count`: construct `GroupOut(..., receiver_count=3)`, assert field equals `3`.
  3. Add e2e test: create admin, create a group, create 2 receivers in it (reuse the create-receiver request pattern at `tests/e2e/test_user_group_memberships.py:163`), then `GET /api/v1/groups` and assert the created group's `receiver_count == 2`; assert `GET /api/v1/groups/{id}` returns the same count; assert `POST /api/v1/groups` (empty group) returns `receiver_count == 0`.
- **Unit tests:** `test_group_out_schema` — updated; `test_group_out_schema_receiver_count` — asserts field `3`.
- **e2e tests:** T-GRP1 (from 1.1) — full assertion set.
- **Done:** `make gates` passes; e2e suite passes (`cd backend && pytest -q -m e2e` and unit suite `-m unit`).

---

## Phase gates

- **Fmt:** `cd backend && ruff format --check .`
- **Lint:** `cd backend && ruff check .`
- **Types:** `cd backend && mypy`
- **Test subset:** `cd backend && pytest -q -m unit && pytest -q -m e2e`
- **Regression guard:** T-GRP1 passes; all pre-existing backend tests still pass (`make gates`).

## Phase done criterion

`GET /api/v1/groups` and `GET /api/v1/groups/{group_id}` responses include an
integer `receiver_count` equal to the number of receivers in the group (0 for
empty groups), all existing backend tests pass, and `make gates` is green.
