"""Receiver e SeverityRule (spec 9.3): CRUD, rotate-slug, test-severity."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_claims, db, require_admin, require_member
from app.core.errors import PROBLEM_TYPES, Problem
from app.core.security import AccessClaims
from app.core.urls import ingest_url, public_base_url
from app.models.group import Group
from app.models.receiver import Receiver
from app.models.severity_preset import (
    ReceiverSeverityPreset,
    SeverityPreset,
    SeverityPresetRule,
)
from app.models.severity_rule import SeverityRule
from app.models.tenant import Tenant
from app.schemas.preset import (
    ReceiverPresetOut,
    ReceiverPresetsIn,
    SeverityChainItemOut,
)
from app.schemas.receiver import (
    DURATION_POLICY_HALF_CONFIGURED,
    DeleteImpactOut,
    ReceiverCreate,
    ReceiverOut,
    ReceiverUpdate,
    SeverityReplayItemOut,
    SeverityReplayOut,
    SeverityRuleCreate,
    SeverityRuleOut,
    SeverityRuleReorderIn,
    SeverityRuleUpdate,
    TestSeverityIn,
    TestSeverityOut,
    _validate_expected_fields,
)
from app.services.authz import accessible_group_ids, assert_group_access
from app.services.rule_chain import load_evaluation_chain
from app.services.severity import InvalidPatternError, compile_pattern, resolve_severity_async
from app.services.slug import build_receiver_slug
from app.services.surveillance import alert_deadline, schedule_from_receiver
from app.services.wrapper_script import (
    WrapperTemplateError,
    load_template,
    render_wrapper_script,
    script_filename,
)

router = APIRouter(tags=["receivers"])


def _receiver_out(receiver: Receiver, request: Request) -> ReceiverOut:
    """ReceiverOut con l'URL di ingestion risolta sulla richiesta in corso:
    dietro reverse proxy e' l'unico posto che sa a quale nome ha risposto
    l'istanza, e il valore deve coincidere con quello dello script scaricabile."""
    out = ReceiverOut.model_validate(receiver)
    out.ingest_url = ingest_url(receiver.slug, request)

    # Scadenza dell'attesa: il conto con l'espressione cron e il suo fuso non si
    # fa nel browser, e la dashboard deve mostrare la stessa data che usa il job.
    schedule = schedule_from_receiver(receiver)
    if schedule is not None:
        reference = receiver.last_notification_at or receiver.expected_since
        if reference is not None:
            now = datetime.now(UTC)
            deadline = alert_deadline(schedule, reference=reference, now=now)
            out.expected_deadline_at = deadline
            out.expected_late = now > deadline
    return out


def _apply_expected_policy(receiver: Receiver, body: ReceiverUpdate) -> None:
    """Politica di attesa in PATCH, verificata sullo stato FINALE.

    Vale lo stesso ragionamento della coppia della durata: una PATCH puo toccare
    uno solo dei cinque campi lasciando gli altri a quello che era salvato,
    quindi il controllo non puo stare nello schema. Qui si ricompone lo stato che
    resterebbe scritto e si rifiuta con 422 leggibile invece di far scattare il
    CHECK del database con un 500.
    """
    fields = (
        "expected_every_seconds",
        "expected_cron",
        "expected_timezone",
        "expected_grace_seconds",
        "missing_severity",
    )
    if not any(field in body.model_fields_set for field in fields):
        return

    final = {
        field: (
            getattr(body, field) if field in body.model_fields_set else getattr(receiver, field)
        )
        for field in fields
    }

    try:
        _validate_expected_fields(
            every_seconds=final["expected_every_seconds"],
            cron=final["expected_cron"],
            timezone=final["expected_timezone"],
            grace_seconds=final["expected_grace_seconds"],
            severity=final["missing_severity"],
        )
    except ValueError as exc:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=str(exc),
        ) from exc

    was_active = receiver.missing_severity is not None
    now_active = final["missing_severity"] is not None
    for field, value in final.items():
        setattr(receiver, field, value)

    if not now_active:
        # Sorveglianza spenta: niente stato residuo, altrimenti riaccendendola
        # si erediterebbe un allarme di mesi prima.
        receiver.expected_since = None
        receiver.missing_alerted_at = None
    elif not was_active:
        # Appena accesa: si conta da adesso, non dall'inizio dei tempi. Un
        # receiver che non ha mai ricevuto niente ha comunque una finestra intera
        # prima del primo allarme.
        receiver.expected_since = datetime.now(UTC)
        receiver.missing_alerted_at = None


async def _get_receiver_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, receiver_id: uuid.UUID
) -> Receiver:
    result = await session.execute(
        select(Receiver).where(
            Receiver.id == receiver_id,
            Receiver.tenant_id == tenant_id,
        )
    )
    receiver = result.scalar_one_or_none()
    if receiver is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Receiver not found.",
        )
    return receiver


async def _get_group_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, group_id: uuid.UUID
) -> Group:
    result = await session.execute(
        select(Group).where(Group.id == group_id, Group.tenant_id == tenant_id)
    )
    group = result.scalar_one_or_none()
    if group is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Group not found.",
        )
    return group


async def _validate_max_body_bytes(
    session: AsyncSession, tenant_id: uuid.UUID, requested: int | None
) -> int:
    tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one()
    if requested is None:
        return tenant.max_body_bytes
    if requested > tenant.max_body_bytes:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail=f"max_body_bytes exceeds tenant cap of {tenant.max_body_bytes} bytes.",
        )
    return requested


@router.post("/groups/{group_id}/receivers", response_model=ReceiverOut, status_code=201)
async def create_receiver(
    group_id: uuid.UUID,
    body: ReceiverCreate,
    request: Request,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    tenant_id = uuid.UUID(claims.tid)
    group = await _get_group_or_404(session, tenant_id, group_id)
    await assert_group_access(session, claims, group_id, write=True)
    max_body_bytes = await _validate_max_body_bytes(session, tenant_id, body.max_body_bytes)

    receiver = Receiver(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        group_id=group_id,
        slug=build_receiver_slug(group.name, body.name),
        name=body.name,
        status="active",
        ingestion_module="http_raw",
        default_severity=body.default_severity,
        exit_code_severity=body.exit_code_severity,
        duration_threshold_seconds=body.duration_threshold_seconds,
        duration_severity=body.duration_severity,
        expected_every_seconds=body.expected_every_seconds,
        expected_cron=body.expected_cron,
        expected_timezone=body.expected_timezone,
        expected_grace_seconds=body.expected_grace_seconds,
        missing_severity=body.missing_severity,
        # L'attesa si conta da adesso: il receiver appena creato non ha ancora
        # ricevuto niente, e senza questo istante il primo controllo non saprebbe
        # da dove misurare.
        expected_since=datetime.now(UTC) if body.missing_severity is not None else None,
        max_body_bytes=max_body_bytes,
        rate_limit_per_min=body.rate_limit_per_min,
    )
    session.add(receiver)
    await session.flush()
    return _receiver_out(receiver, request)


@router.get("/groups/{group_id}/receivers", response_model=list[ReceiverOut])
async def list_receivers(
    group_id: uuid.UUID,
    request: Request,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverOut]:
    await assert_group_access(session, claims, group_id, write=False)
    result = await session.execute(
        select(Receiver)
        .where(
            Receiver.group_id == group_id,
            Receiver.tenant_id == uuid.UUID(claims.tid),
        )
        .order_by(Receiver.name.asc())
    )
    return [_receiver_out(r, request) for r in result.scalars().all()]


@router.get("/receivers", response_model=list[ReceiverOut])
async def list_all_receivers(
    request: Request,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverOut]:
    """Tutti i receiver visibili al chiamante, per i selettori della UI che
    non partono da un gruppo (override per receiver nella pagina Canali)."""
    conditions = [Receiver.tenant_id == uuid.UUID(claims.tid)]
    allowed = await accessible_group_ids(session, claims)
    if allowed is not None:
        if not allowed:
            return []
        conditions.append(Receiver.group_id.in_(allowed))

    result = await session.execute(
        select(Receiver).where(*conditions).order_by(Receiver.name.asc())
    )
    return [_receiver_out(r, request) for r in result.scalars().all()]


@router.get("/receivers/{receiver_id}", response_model=ReceiverOut)
async def get_receiver(
    receiver_id: uuid.UUID,
    request: Request,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    receiver = await _get_receiver_or_404(session, uuid.UUID(claims.tid), receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)
    out = _receiver_out(receiver, request)

    from app.core.redis import get_redis

    redis = await get_redis()
    rejected = await redis.get(f"ingest:rejected:{receiver.id}")
    out.rejected_last_24h = int(rejected) if rejected is not None else 0
    return out


@router.patch("/receivers/{receiver_id}", response_model=ReceiverOut)
async def update_receiver(
    receiver_id: uuid.UUID,
    body: ReceiverUpdate,
    request: Request,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    if body.name is not None:
        receiver.name = body.name
    if body.status is not None:
        receiver.status = body.status
    if body.max_body_bytes is not None:
        receiver.max_body_bytes = await _validate_max_body_bytes(
            session, tenant_id, body.max_body_bytes
        )
    if body.rate_limit_per_min is not None:
        receiver.rate_limit_per_min = body.rate_limit_per_min
    if body.default_severity is not None:
        receiver.default_severity = body.default_severity
    # None qui significa "disattiva la politica sull'exit code", quindi conta
    # se il campo e stato inviato, non se vale None.
    if "exit_code_severity" in body.model_fields_set:
        receiver.exit_code_severity = body.exit_code_severity

    # Soglia di durata: idem per il None, ma la coppia va verificata sullo stato
    # FINALE. Una PATCH che cambia solo la severity su un receiver che ha gia la
    # soglia e legittima; quella che ne lascia una sola valorizzata no, e va
    # respinta qui con un 422 leggibile invece di far scattare il CHECK del
    # database con un 500.
    threshold = receiver.duration_threshold_seconds
    duration_severity = receiver.duration_severity
    if "duration_threshold_seconds" in body.model_fields_set:
        threshold = body.duration_threshold_seconds
    if "duration_severity" in body.model_fields_set:
        duration_severity = body.duration_severity
    if (threshold is None) != (duration_severity is None):
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=DURATION_POLICY_HALF_CONFIGURED,
        )
    receiver.duration_threshold_seconds = threshold
    receiver.duration_severity = duration_severity

    _apply_expected_policy(receiver, body)

    # Il rename NON riscrive lo slug: e' la credenziale con cui gli script in
    # produzione stanno inviando, cambiarla di nascosto li spegnerebbe. Per
    # riallinearlo ai nomi nuovi c'e' rotate-slug (vedi services/slug.py).
    await session.flush()
    return _receiver_out(receiver, request)


@router.delete("/receivers/{receiver_id}", status_code=204)
async def delete_receiver(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    receiver = await _get_receiver_or_404(session, uuid.UUID(claims.tid), receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)
    await session.delete(receiver)


@router.post("/receivers/{receiver_id}/rotate-slug", response_model=ReceiverOut)
async def rotate_slug(
    receiver_id: uuid.UUID,
    request: Request,
    claims: AccessClaims = Depends(require_admin),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> ReceiverOut:
    """Rigenera lo slug. Ad admin+ anche se il member puo creare receiver:
    rigenerare uno slug rompe gli script gia in produzione (spec 4.1).

    Il token casuale e' nuovo e il prefisso viene ricostruito sui nomi ATTUALI
    di gruppo e receiver: e' anche il modo per allineare lo slug dopo un rename,
    e per dare la forma parlante a un receiver creato prima della 0011."""
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    group = await _get_group_or_404(session, tenant_id, receiver.group_id)
    receiver.slug = build_receiver_slug(group.name, receiver.name)
    await session.flush()
    return _receiver_out(receiver, request)


@router.get("/receivers/{receiver_id}/wrapper-script", response_class=Response)
async def download_wrapper_script(
    receiver_id: uuid.UUID,
    request: Request,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> Response:
    """`scripts/notifyhub-run.sh` con URL e slug di questo receiver gia' dentro.

    Serve lo stesso file del repository, con riscritte le due righe del blocco
    "configurazione": nessuna seconda copia dello script da tenere allineata, e
    l'URL e' quella pubblica risolta sulla richiesta, cioe' quella che vede il
    browser dell'operatore (reverse proxy e https compresi).

    Basta il permesso di lettura sul gruppo: lo script contiene lo slug, che la
    pagina del receiver mostra comunque a chiunque possa vederla.
    """
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)
    group = await _get_group_or_404(session, tenant_id, receiver.group_id)

    try:
        script = render_wrapper_script(
            load_template(),
            base_url=public_base_url(request),
            slug=receiver.slug,
            receiver_name=receiver.name,
            group_name=group.name,
        )
    except WrapperTemplateError as exc:
        raise Problem(
            status=500,
            type=PROBLEM_TYPES["internal_error"],
            title="Internal Server Error",
            detail=f"Wrapper script template unavailable: {exc}",
        ) from exc

    return Response(
        content=script,
        media_type="text/x-shellscript; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{script_filename(receiver.name)}"',
            # Contiene la credenziale di ingestion: fuori da ogni cache.
            "Cache-Control": "no-store",
        },
    )


@router.get("/receivers/{receiver_id}/severity-rules", response_model=list[SeverityRuleOut])
async def list_severity_rules(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[SeverityRuleOut]:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)

    result = await session.execute(
        select(SeverityRule)
        .where(
            SeverityRule.receiver_id == receiver_id,
            SeverityRule.tenant_id == tenant_id,
        )
        .order_by(SeverityRule.priority.asc())
    )
    return [SeverityRuleOut.model_validate(r) for r in result.scalars().all()]


async def _next_priority(
    session: AsyncSession, tenant_id: uuid.UUID, receiver_id: uuid.UUID
) -> int:
    """Accoda la nuova regola in fondo, lasciando spazio per inserirne altre in
    mezzo domani (10, 20, 30...)."""
    result = await session.execute(
        select(func.max(SeverityRule.priority)).where(
            SeverityRule.receiver_id == receiver_id,
            SeverityRule.tenant_id == tenant_id,
        )
    )
    current_max = result.scalar_one()
    return 10 if current_max is None else current_max + 10


async def _assert_priority_free(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    receiver_id: uuid.UUID,
    priority: int,
    *,
    exclude_rule_id: uuid.UUID | None = None,
) -> None:
    """Il vincolo di unicita e nel database (migrazione 0008): qui il conflitto
    diventa un messaggio che dice quale numero e occupato, invece del 409
    generico dell'IntegrityError."""
    conditions = [
        SeverityRule.receiver_id == receiver_id,
        SeverityRule.tenant_id == tenant_id,
        SeverityRule.priority == priority,
    ]
    if exclude_rule_id is not None:
        conditions.append(SeverityRule.id != exclude_rule_id)

    result = await session.execute(select(SeverityRule.id).where(*conditions))
    if result.scalar_one_or_none() is not None:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail=(
                f"Priority {priority} is already used by another rule on this receiver. "
                "Priorities must be unique: the lowest one is evaluated first."
            ),
        )


@router.post(
    "/receivers/{receiver_id}/severity-rules", response_model=SeverityRuleOut, status_code=201
)
async def create_severity_rule(
    receiver_id: uuid.UUID,
    body: SeverityRuleCreate,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityRuleOut:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    try:
        compile_pattern(body.pattern, body.case_insensitive)
    except InvalidPatternError as exc:
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail=f"Pattern not compilable by RE2: {exc}",
        ) from exc

    if body.priority is None:
        priority = await _next_priority(session, tenant_id, receiver_id)
    else:
        priority = body.priority
        await _assert_priority_free(session, tenant_id, receiver_id, priority)

    rule = SeverityRule(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        receiver_id=receiver_id,
        priority=priority,
        pattern=body.pattern,
        case_insensitive=body.case_insensitive,
        severity=body.severity,
        enabled=body.enabled,
    )
    session.add(rule)
    await session.flush()
    return SeverityRuleOut.model_validate(rule)


async def _get_rule_or_404(
    session: AsyncSession, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> SeverityRule:
    result = await session.execute(
        select(SeverityRule).where(
            SeverityRule.id == rule_id,
            SeverityRule.tenant_id == tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise Problem(
            status=404,
            type=PROBLEM_TYPES["not_found"],
            title="Not Found",
            detail="Severity rule not found.",
        )
    return rule


@router.put("/receivers/{receiver_id}/severity-rules/order", response_model=list[SeverityRuleOut])
async def reorder_severity_rules(
    receiver_id: uuid.UUID,
    body: SeverityRuleReorderIn,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[SeverityRuleOut]:
    """Rinumera le regole 10, 20, 30... nell'ordine dato. Sposta una regola in
    su o in giu senza far calcolare al chiamante un numero di priorita libero.

    La rinumerazione avviene in due passate: prima tutte le priorita vanno su
    valori negativi, poi su quelli definitivi. Un singolo UPDATE che scambia
    due valori violerebbe il vincolo di unicita mentre e a meta strada, perche
    Postgres lo verifica riga per riga e non a fine istruzione.
    """
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    result = await session.execute(
        select(SeverityRule).where(
            SeverityRule.receiver_id == receiver_id,
            SeverityRule.tenant_id == tenant_id,
        )
    )
    rules = {rule.id: rule for rule in result.scalars().all()}

    if set(body.rule_ids) != set(rules.keys()):
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="rule_ids must list every rule of this receiver exactly once.",
        )

    for index, rule_id in enumerate(body.rule_ids):
        rules[rule_id].priority = -(index + 1)
    await session.flush()

    for index, rule_id in enumerate(body.rule_ids):
        rules[rule_id].priority = (index + 1) * 10
    await session.flush()

    return [SeverityRuleOut.model_validate(rules[rule_id]) for rule_id in body.rule_ids]


@router.patch("/severity-rules/{rule_id}", response_model=SeverityRuleOut)
async def update_severity_rule(
    rule_id: uuid.UUID,
    body: SeverityRuleUpdate,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityRuleOut:
    tenant_id = uuid.UUID(claims.tid)
    rule = await _get_rule_or_404(session, tenant_id, rule_id)
    receiver = await _get_receiver_or_404(session, tenant_id, rule.receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    new_pattern = body.pattern if body.pattern is not None else rule.pattern
    new_case_insensitive = (
        body.case_insensitive if body.case_insensitive is not None else rule.case_insensitive
    )
    if body.pattern is not None or body.case_insensitive is not None:
        try:
            compile_pattern(new_pattern, new_case_insensitive)
        except InvalidPatternError as exc:
            raise Problem(
                status=422,
                type=PROBLEM_TYPES["validation_error"],
                title="Validation Error",
                detail=f"Pattern not compilable by RE2: {exc}",
            ) from exc

    if body.priority is not None and body.priority != rule.priority:
        await _assert_priority_free(
            session, tenant_id, rule.receiver_id, body.priority, exclude_rule_id=rule.id
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
    return SeverityRuleOut.model_validate(rule)


@router.delete("/severity-rules/{rule_id}", status_code=204)
async def delete_severity_rule(
    rule_id: uuid.UUID,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> None:
    tenant_id = uuid.UUID(claims.tid)
    rule = await _get_rule_or_404(session, tenant_id, rule_id)
    receiver = await _get_receiver_or_404(session, tenant_id, rule.receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)
    await session.delete(rule)


@router.post("/receivers/{receiver_id}/test-severity", response_model=TestSeverityOut)
async def test_severity(
    receiver_id: uuid.UUID,
    body: TestSeverityIn,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> TestSeverityOut:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)

    rules = await load_evaluation_chain(session, tenant_id, receiver_id)

    resolution = await resolve_severity_async(
        header_severity=body.header_severity,
        query_severity=None,
        rules=rules,
        content=body.content,
        default_severity=receiver.default_severity,
        exit_code=body.exit_code,
        exit_code_severity=receiver.exit_code_severity,
        duration_ms=body.duration_ms,
        duration_threshold_seconds=receiver.duration_threshold_seconds,
        duration_severity=receiver.duration_severity,
    )

    return TestSeverityOut(
        severity=resolution.severity,
        source=resolution.source.value,
        matched_rule_id=resolution.matched_rule_id,
        matched_pattern=resolution.matched_pattern,
        matched_preset_id=resolution.matched_preset_id,
        matched_preset_name=resolution.matched_preset_name,
        duration_exceeded=resolution.duration_exceeded,
    )


REPLAY_PREVIEW_CHARS = 200
REPLAY_MAX_NOTIFICATIONS = 20


@router.get("/receivers/{receiver_id}/severity-rules/replay", response_model=SeverityReplayOut)
async def replay_severity_rules(
    receiver_id: uuid.UUID,
    limit: int = Query(default=10, ge=1, le=REPLAY_MAX_NOTIFICATIONS),  # noqa: B008
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> SeverityReplayOut:
    """Rivaluta le ultime notifiche del receiver con le regole ATTUALI e
    confronta il risultato con la severity registrata all'epoca.

    Serve a rispondere alla domanda che la casella "Prova severity" non copre:
    non "cosa succederebbe a questo testo che mi invento", ma "cosa cambierebbe
    sui messaggi che arrivano davvero".
    """
    from app.models.notification import Notification

    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)

    rules = await load_evaluation_chain(session, tenant_id, receiver_id)

    notifications_result = await session.execute(
        select(Notification)
        .where(Notification.receiver_id == receiver_id, Notification.tenant_id == tenant_id)
        .order_by(Notification.received_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    notifications = list(notifications_result.scalars().all())

    items: list[SeverityReplayItemOut] = []
    for notification in notifications:
        content = notification.content
        truncated = False
        if content is None:
            # Payload su object storage: rileggerlo per intero moltiplicherebbe
            # le richieste a MinIO. Si rivaluta l'anteprima, segnalando che il
            # risultato riguarda solo quella parte.
            content = notification.content_preview
            truncated = True

        # Rivalutazione della catena INTERA, non solo delle regole: exit code e
        # durata di quella esecuzione sono persistiti sulla notifica, quindi il
        # replay li rimette in gioco con le politiche di adesso. Senza, una
        # notifica decisa dall'exit code risulterebbe sempre "cambiata" solo
        # perche il replay non sapeva che il comando era fallito.
        resolution = await resolve_severity_async(
            header_severity=None,
            query_severity=None,
            rules=rules,
            content=content,
            default_severity=receiver.default_severity,
            exit_code=notification.exit_code,
            exit_code_severity=receiver.exit_code_severity,
            duration_ms=notification.duration_ms,
            duration_threshold_seconds=receiver.duration_threshold_seconds,
            duration_severity=receiver.duration_severity,
        )
        items.append(
            SeverityReplayItemOut(
                notification_id=notification.id,
                received_at=notification.received_at,
                content_preview=notification.content_preview[:REPLAY_PREVIEW_CHARS],
                truncated=truncated,
                stored_severity=notification.severity,
                stored_source=notification.severity_source,
                replayed_severity=resolution.severity,
                replayed_source=resolution.source.value,
                matched_rule_id=resolution.matched_rule_id,
                matched_pattern=resolution.matched_pattern,
                matched_preset_name=resolution.matched_preset_name,
                changed=resolution.severity != notification.severity,
            )
        )

    return SeverityReplayOut(items=items, changed_count=sum(1 for item in items if item.changed))


async def _receiver_presets(
    session: AsyncSession, tenant_id: uuid.UUID, receiver_id: uuid.UUID
) -> list[ReceiverPresetOut]:
    result = await session.execute(
        select(SeverityPreset, ReceiverSeverityPreset.position)
        .join(ReceiverSeverityPreset, ReceiverSeverityPreset.preset_id == SeverityPreset.id)
        .where(
            ReceiverSeverityPreset.receiver_id == receiver_id,
            ReceiverSeverityPreset.tenant_id == tenant_id,
        )
        .order_by(ReceiverSeverityPreset.position.asc())
    )
    rows = result.all()
    if not rows:
        return []

    counts_result = await session.execute(
        select(SeverityPresetRule.preset_id, func.count())
        .where(SeverityPresetRule.preset_id.in_([preset.id for preset, _ in rows]))
        .group_by(SeverityPresetRule.preset_id)
    )
    counts = {row[0]: row[1] for row in counts_result.all()}

    return [
        ReceiverPresetOut(
            preset_id=preset.id,
            name=preset.name,
            description=preset.description,
            builtin_key=preset.builtin_key,
            position=position,
            rules_count=counts.get(preset.id, 0),
        )
        for preset, position in rows
    ]


@router.get("/receivers/{receiver_id}/presets", response_model=list[ReceiverPresetOut])
async def list_receiver_presets(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverPresetOut]:
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)
    return await _receiver_presets(session, tenant_id, receiver_id)


@router.put("/receivers/{receiver_id}/presets", response_model=list[ReceiverPresetOut])
async def set_receiver_presets(
    receiver_id: uuid.UUID,
    body: ReceiverPresetsIn,
    claims: AccessClaims = Depends(require_member),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[ReceiverPresetOut]:
    """Sostituisce l'elenco dei preset applicati al receiver.

    Il corpo e l'elenco completo nell'ordine di valutazione voluto: quello che
    non compare viene staccato. Applicare i preset e una modifica al receiver,
    non al preset, quindi basta il ruolo member sul gruppo del receiver.
    """
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=True)

    if len(set(body.preset_ids)) != len(body.preset_ids):
        raise Problem(
            status=422,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="preset_ids contains the same preset more than once.",
        )

    if body.preset_ids:
        found_result = await session.execute(
            select(SeverityPreset.id).where(
                SeverityPreset.id.in_(body.preset_ids),
                SeverityPreset.tenant_id == tenant_id,
            )
        )
        found = {row[0] for row in found_result.all()}
        missing = [str(pid) for pid in body.preset_ids if pid not in found]
        if missing:
            raise Problem(
                status=404,
                type=PROBLEM_TYPES["not_found"],
                title="Not Found",
                detail=f"Severity preset not found: {', '.join(missing)}.",
            )

    # DELETE esplicito e flush prima degli INSERT: l'unita di lavoro di
    # SQLAlchemy emetterebbe gli INSERT per primi, e il vincolo di unicita su
    # (receiver_id, position) scatterebbe su una posizione ancora occupata.
    await session.execute(
        delete(ReceiverSeverityPreset).where(
            ReceiverSeverityPreset.receiver_id == receiver_id,
            ReceiverSeverityPreset.tenant_id == tenant_id,
        )
    )
    await session.flush()

    for position, preset_id in enumerate(body.preset_ids):
        session.add(
            ReceiverSeverityPreset(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                receiver_id=receiver_id,
                preset_id=preset_id,
                position=position,
            )
        )
    await session.flush()

    return await _receiver_presets(session, tenant_id, receiver_id)


@router.get("/receivers/{receiver_id}/severity-chain", response_model=list[SeverityChainItemOut])
async def get_severity_chain(
    receiver_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> list[SeverityChainItemOut]:
    """La catena effettiva: tutte le regole attive del receiver, proprie e dei
    preset, nell'ordine esatto in cui vengono provate. Risponde alla domanda
    "quale regola decide" senza doverla ricostruire a mente da due elenchi."""
    tenant_id = uuid.UUID(claims.tid)
    receiver = await _get_receiver_or_404(session, tenant_id, receiver_id)
    await assert_group_access(session, claims, receiver.group_id, write=False)

    chain = await load_evaluation_chain(session, tenant_id, receiver_id)
    return [
        SeverityChainItemOut(
            position=index + 1,
            rule_id=uuid.UUID(rule.id),
            pattern=rule.pattern,
            case_insensitive=rule.case_insensitive,
            severity=rule.severity,
            origin="preset" if rule.preset_id is not None else "receiver",
            preset_id=uuid.UUID(rule.preset_id) if rule.preset_id is not None else None,
            preset_name=rule.preset_name,
        )
        for index, rule in enumerate(chain)
    ]


@router.get("/groups/{group_id}/delete-impact", response_model=DeleteImpactOut)
async def group_delete_impact(
    group_id: uuid.UUID,
    claims: AccessClaims = Depends(current_claims),  # noqa: B008
    session: AsyncSession = Depends(db),  # noqa: B008
) -> DeleteImpactOut:
    """Preflight per la cancellazione di un gruppo (spec 9.3): conteggi reali
    di receiver, notifiche e delivery che verrebbero eliminati in cascata."""
    from app.models.delivery import Delivery
    from app.models.notification import Notification

    tenant_id = uuid.UUID(claims.tid)
    await assert_group_access(session, claims, group_id, write=False)

    receivers_result = await session.execute(
        select(Receiver.id).where(Receiver.group_id == group_id, Receiver.tenant_id == tenant_id)
    )
    receiver_ids = [row[0] for row in receivers_result.all()]

    if not receiver_ids:
        return DeleteImpactOut(receivers=0, notifications=0, deliveries=0)

    notifications_result = await session.execute(
        select(Notification.id).where(
            Notification.receiver_id.in_(receiver_ids), Notification.tenant_id == tenant_id
        )
    )
    notification_ids = [row[0] for row in notifications_result.all()]

    deliveries_count = 0
    if notification_ids:
        deliveries_result = await session.execute(
            select(Delivery.id).where(
                Delivery.notification_id.in_(notification_ids), Delivery.tenant_id == tenant_id
            )
        )
        deliveries_count = len(deliveries_result.all())

    return DeleteImpactOut(
        receivers=len(receiver_ids),
        notifications=len(notification_ids),
        deliveries=deliveries_count,
    )
