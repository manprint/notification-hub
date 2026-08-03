"""Preset di regole di severity: insiemi riusabili applicabili a piu receiver.

Un preset e dati del tenant come tutto il resto: quelli predefiniti nascono da
una copia del catalogo (services/severity_presets.py) e da quel momento si
modificano liberamente. La scrittura richiede admin perche un preset e condiviso
fra gruppi: chi lo cambia tocca receiver che non necessariamente gestisce. La
lettura e aperta a tutti i ruoli.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.models.severity_preset import (
    ReceiverSeverityPreset,
    SeverityPreset,
    SeverityPresetRule,
)
from app.schemas.preset import (
    BuiltinPresetOut,
    SeverityPresetCreate,
    SeverityPresetDetailOut,
    SeverityPresetOut,
    SeverityPresetRuleCreate,
    SeverityPresetRuleOut,
    SeverityPresetRuleReorderIn,
    SeverityPresetRuleUpdate,
    SeverityPresetUpdate,
    SyncBuiltinPresetsOut,
)
from app.services.severity import InvalidPatternError, compile_pattern
from app.services.severity_presets import (
    BUILTIN_PRESETS,
    PRIORITY_STEP,
    reset_preset_to_builtin,
    sync_builtin_presets,
)

router = APIRouter(tags=["severity-presets"])


async def _get_preset_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, preset_id: uuid.UUID
) -> SeverityPreset:
    result = await session.execute(
        select(SeverityPreset).where(
            SeverityPreset.id == preset_id,
            SeverityPreset.tenant_id == tenant_id,
        )
    )
    preset = result.scalar_one_or_none()
    if preset is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Severity preset not found.",
        )
    return preset


async def _rules_of(session: AsyncSession, preset_id: uuid.UUID) -> list[SeverityPresetRule]:
    result = await session.execute(
        select(SeverityPresetRule)
        .where(SeverityPresetRule.preset_id == preset_id)
        .order_by(SeverityPresetRule.priority.asc())
    )
    return list(result.scalars().all())


async def _detail(session: AsyncSession, preset: SeverityPreset) -> SeverityPresetDetailOut:
    rules = await _rules_of(session, preset.id)
    receivers = await session.execute(
        select(func.count())
        .select_from(ReceiverSeverityPreset)
        .where(ReceiverSeverityPreset.preset_id == preset.id)
    )
    return SeverityPresetDetailOut(
        id=preset.id,
        builtin_key=preset.builtin_key,
        name=preset.name,
        description=preset.description,
        rules_count=len(rules),
        receivers_count=receivers.scalar_one(),
        rules=[SeverityPresetRuleOut.model_validate(rule) for rule in rules],
    )


def _validate_pattern(pattern: str, case_insensitive: bool) -> None:
    try:
        compile_pattern(pattern, case_insensitive)
    except InvalidPatternError as exc:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=f"Pattern not compilable by RE2: {exc}",
        ) from exc


async def _assert_name_free(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    *,
    exclude_preset_id: uuid.UUID | None = None,
) -> None:
    conditions = [SeverityPreset.tenant_id == tenant_id, SeverityPreset.name == name]
    if exclude_preset_id is not None:
        conditions.append(SeverityPreset.id != exclude_preset_id)
    result = await session.execute(select(SeverityPreset.id).where(*conditions))
    if result.scalar_one_or_none() is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail=f"A preset named '{name}' already exists.",
        )


@router.get("/severity-presets", response_model=list[SeverityPresetOut])
async def list_presets(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[SeverityPresetOut]:
    tenant_id = uuid.UUID(claims.tid)

    presets_result = await session.execute(
        select(SeverityPreset)
        .where(SeverityPreset.tenant_id == tenant_id)
        .order_by(SeverityPreset.name.asc())
    )
    presets = list(presets_result.scalars().all())

    # Due aggregazioni separate invece di una query con due outer join: unire i
    # conteggi di regole e receiver nella stessa query li moltiplicherebbe fra
    # loro (prodotto cartesiano delle due relazioni).
    rules_result = await session.execute(
        select(SeverityPresetRule.preset_id, func.count())
        .where(SeverityPresetRule.tenant_id == tenant_id)
        .group_by(SeverityPresetRule.preset_id)
    )
    rules_by_preset = {row[0]: row[1] for row in rules_result.all()}

    receivers_result = await session.execute(
        select(ReceiverSeverityPreset.preset_id, func.count())
        .where(ReceiverSeverityPreset.tenant_id == tenant_id)
        .group_by(ReceiverSeverityPreset.preset_id)
    )
    receivers_by_preset = {row[0]: row[1] for row in receivers_result.all()}

    return [
        SeverityPresetOut(
            id=preset.id,
            builtin_key=preset.builtin_key,
            name=preset.name,
            description=preset.description,
            rules_count=rules_by_preset.get(preset.id, 0),
            receivers_count=receivers_by_preset.get(preset.id, 0),
        )
        for preset in presets
    ]


@router.get("/severity-presets/catalog", response_model=list[BuiltinPresetOut])
async def list_builtin_catalog(
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[BuiltinPresetOut]:
    """Il catalogo dei preset predefiniti con l'indicazione di quali sono gia
    installati in questo tenant. Serve alla dashboard per proporre
    l'installazione dei mancanti dopo un aggiornamento."""
    tenant_id = uuid.UUID(claims.tid)
    result = await session.execute(
        select(SeverityPreset.builtin_key).where(
            SeverityPreset.tenant_id == tenant_id,
            SeverityPreset.builtin_key.is_not(None),
        )
    )
    installed = {row[0] for row in result.all()}
    return [
        BuiltinPresetOut(
            key=spec.key,
            name=spec.name,
            description=spec.description,
            rules_count=len(spec.rules),
            installed=spec.key in installed,
        )
        for spec in BUILTIN_PRESETS
    ]


@router.post("/severity-presets/sync-builtin", response_model=SyncBuiltinPresetsOut)
async def sync_builtin(
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SyncBuiltinPresetsOut:
    """Installa i preset del catalogo che mancano a questo tenant.

    Non tocca le copie gia presenti, nemmeno se modificate: e un'operazione
    additiva, ripetibile senza effetti collaterali.
    """
    tenant_id = uuid.UUID(claims.tid)
    before = {spec.key for spec in BUILTIN_PRESETS}
    installed = await sync_builtin_presets(session, tenant_id)
    return SyncBuiltinPresetsOut(
        installed=installed,
        already_present=sorted(before - set(installed)),
    )


@router.post("/severity-presets", response_model=SeverityPresetDetailOut, status_code=201)
async def create_preset(
    body: SeverityPresetCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityPresetDetailOut:
    tenant_id = uuid.UUID(claims.tid)
    await _assert_name_free(session, tenant_id, body.name)

    preset = SeverityPreset(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        builtin_key=None,
        name=body.name,
        description=body.description,
    )
    session.add(preset)
    await session.flush()
    return await _detail(session, preset)


@router.get("/severity-presets/{preset_id}", response_model=SeverityPresetDetailOut)
async def get_preset(
    preset_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityPresetDetailOut:
    preset = await _get_preset_or_404(session, uuid.UUID(claims.tid), preset_id)
    return await _detail(session, preset)


@router.patch("/severity-presets/{preset_id}", response_model=SeverityPresetDetailOut)
async def update_preset(
    preset_id: uuid.UUID,
    body: SeverityPresetUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityPresetDetailOut:
    tenant_id = uuid.UUID(claims.tid)
    preset = await _get_preset_or_404(session, tenant_id, preset_id)

    if body.name is not None and body.name != preset.name:
        await _assert_name_free(session, tenant_id, body.name, exclude_preset_id=preset.id)
        preset.name = body.name
    if body.description is not None:
        preset.description = body.description

    await session.flush()
    return await _detail(session, preset)


@router.delete("/severity-presets/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    """Elimina il preset. Le regole e le associazioni ai receiver spariscono in
    cascata: i receiver che lo usavano tornano a valutare solo le proprie
    regole, senza restare con un riferimento morto."""
    preset = await _get_preset_or_404(session, uuid.UUID(claims.tid), preset_id)
    await session.delete(preset)


@router.post("/severity-presets/{preset_id}/reset", response_model=SeverityPresetDetailOut)
async def reset_preset(
    preset_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityPresetDetailOut:
    """Riporta un preset predefinito ai valori del catalogo, scartando le
    modifiche locali."""
    preset = await _get_preset_or_404(session, uuid.UUID(claims.tid), preset_id)
    try:
        await reset_preset_to_builtin(session, preset)
    except KeyError as exc:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="This preset was not created from a builtin one: there is nothing to restore.",
        ) from exc
    return await _detail(session, preset)


async def _next_rule_priority(session: AsyncSession, preset_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.max(SeverityPresetRule.priority)).where(
            SeverityPresetRule.preset_id == preset_id
        )
    )
    current_max = result.scalar_one()
    return PRIORITY_STEP if current_max is None else current_max + PRIORITY_STEP


async def _assert_rule_priority_free(
    session: AsyncSession,
    preset_id: uuid.UUID,
    priority: int,
    *,
    exclude_rule_id: uuid.UUID | None = None,
) -> None:
    conditions = [
        SeverityPresetRule.preset_id == preset_id,
        SeverityPresetRule.priority == priority,
    ]
    if exclude_rule_id is not None:
        conditions.append(SeverityPresetRule.id != exclude_rule_id)
    result = await session.execute(select(SeverityPresetRule.id).where(*conditions))
    if result.scalar_one_or_none() is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail=(
                f"Priority {priority} is already used by another rule in this preset. "
                "Priorities must be unique: the lowest one is evaluated first."
            ),
        )


@router.post(
    "/severity-presets/{preset_id}/rules", response_model=SeverityPresetRuleOut, status_code=201
)
async def create_preset_rule(
    preset_id: uuid.UUID,
    body: SeverityPresetRuleCreate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityPresetRuleOut:
    tenant_id = uuid.UUID(claims.tid)
    preset = await _get_preset_or_404(session, tenant_id, preset_id)
    _validate_pattern(body.pattern, body.case_insensitive)

    if body.priority is None:
        priority = await _next_rule_priority(session, preset.id)
    else:
        priority = body.priority
        await _assert_rule_priority_free(session, preset.id, priority)

    rule = SeverityPresetRule(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        preset_id=preset.id,
        priority=priority,
        pattern=body.pattern,
        case_insensitive=body.case_insensitive,
        severity=body.severity,
        enabled=body.enabled,
    )
    session.add(rule)
    await session.flush()
    return SeverityPresetRuleOut.model_validate(rule)


@router.put("/severity-presets/{preset_id}/rules/order", response_model=list[SeverityPresetRuleOut])
async def reorder_preset_rules(
    preset_id: uuid.UUID,
    body: SeverityPresetRuleReorderIn,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[SeverityPresetRuleOut]:
    """Rinumera le regole del preset nell'ordine dato.

    Due passate, come per le regole dei receiver: prima priorita negative, poi
    quelle definitive. Un solo UPDATE che scambia due valori violerebbe il
    vincolo di unicita mentre e a meta strada.
    """
    tenant_id = uuid.UUID(claims.tid)
    preset = await _get_preset_or_404(session, tenant_id, preset_id)

    rules = {rule.id: rule for rule in await _rules_of(session, preset.id)}
    if set(body.rule_ids) != set(rules.keys()):
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="rule_ids must list every rule of this preset exactly once.",
        )

    for index, rule_id in enumerate(body.rule_ids):
        rules[rule_id].priority = -(index + 1)
    await session.flush()

    for index, rule_id in enumerate(body.rule_ids):
        rules[rule_id].priority = (index + 1) * PRIORITY_STEP
    await session.flush()

    return [SeverityPresetRuleOut.model_validate(rules[rule_id]) for rule_id in body.rule_ids]


async def _get_preset_rule_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> SeverityPresetRule:
    result = await session.execute(
        select(SeverityPresetRule).where(
            SeverityPresetRule.id == rule_id,
            SeverityPresetRule.tenant_id == tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Preset rule not found.",
        )
    return rule


@router.patch("/severity-preset-rules/{rule_id}", response_model=SeverityPresetRuleOut)
async def update_preset_rule(
    rule_id: uuid.UUID,
    body: SeverityPresetRuleUpdate,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityPresetRuleOut:
    tenant_id = uuid.UUID(claims.tid)
    rule = await _get_preset_rule_or_404(session, tenant_id, rule_id)

    if body.pattern is not None or body.case_insensitive is not None:
        _validate_pattern(
            body.pattern if body.pattern is not None else rule.pattern,
            body.case_insensitive if body.case_insensitive is not None else rule.case_insensitive,
        )

    if body.priority is not None and body.priority != rule.priority:
        await _assert_rule_priority_free(
            session, rule.preset_id, body.priority, exclude_rule_id=rule.id
        )
        rule.priority = body.priority
    if body.pattern is not None:
        rule.pattern = body.pattern
    if body.case_insensitive is not None:
        rule.case_insensitive = body.case_insensitive
    if body.severity is not None:
        rule.severity = body.severity
    if body.enabled is not None:
        rule.enabled = body.enabled

    await session.flush()
    return SeverityPresetRuleOut.model_validate(rule)


@router.delete("/severity-preset-rules/{rule_id}", status_code=204)
async def delete_preset_rule(
    rule_id: uuid.UUID,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    rule = await _get_preset_rule_or_404(session, uuid.UUID(claims.tid), rule_id)
    await session.delete(rule)
