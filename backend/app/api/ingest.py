"""POST /ingest/{slug} — endpoint pubblico del modulo http_raw (spec 6.2, 9.1).

Montato senza prefisso /api/v1: lo slug e l'unica credenziale (spec, glossario).
"""

import asyncio

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import PROBLEM_TYPES, Problem, ingest_not_found
from app.core.logging import get_logger
from app.core.metrics import ingestion_requests_total
from app.core.redis import get_redis
from app.db.session import tenant_session
from app.db.types import TenantStatus
from app.schemas.ingestion import IngestResponse
from app.services.idempotency import release, reserve, store_response
from app.services.ingest import (
    persist_notification,
    prepare_notification,
    resolve_receiver_by_slug,
)
from app.services.quota import enforce_tenant_quotas
from app.services.ratelimit import check_ip_rate_limit, check_slug_rate_limit
from app.services.severity import parse_duration_ms, parse_exit_code, parse_phase

logger = get_logger(__name__)
router = APIRouter(tags=["ingest"])


def _source_ip(request: Request) -> str:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    if client_host in settings.trusted_proxies_list:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return client_host


_ACCEPTED_MEDIA_TYPES = {"text/plain", "application/x-www-form-urlencoded"}


def _validate_content_type(content_type: str | None) -> None:
    if not content_type:
        return
    media_type = content_type.split(";", 1)[0].strip().lower()
    # curl --data e wget --post-data, i due client citati dalla spec 6.2, impostano
    # da soli Content-Type: application/x-www-form-urlencoded quando non lo si
    # specifica esplicitamente: va accettato allo stesso modo di text/plain,
    # altrimenti nessuno degli esempi curl della spec funzionerebbe davvero.
    if media_type not in _ACCEPTED_MEDIA_TYPES:
        raise Problem(
            status=415,
            type=PROBLEM_TYPES["unsupported_media_type"],
            title="Unsupported Media Type",
            detail="Only text/plain is accepted by the http_raw ingestion module.",
        )


async def _read_body_streaming(request: Request, max_bytes: int) -> bytes:
    """Streaming con interruzione anticipata (spec 6.5): non bufferizza mai piu
    di max_bytes prima di rispondere 413."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise Problem(
                status=413,
                type=PROBLEM_TYPES["payload_too_large"],
                title="Payload Too Large",
                detail=f"Body exceeds {max_bytes} bytes.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/ingest/{slug}", response_model=IngestResponse)
async def ingest(
    slug: str,
    request: Request,
    x_severity: str | None = Header(default=None, alias="X-Severity"),  # noqa: B008
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),  # noqa: B008
    x_exit_code: str | None = Header(default=None, alias="X-Exit-Code"),  # noqa: B008
    x_duration_ms: str | None = Header(default=None, alias="X-Duration-Ms"),  # noqa: B008
    x_phase: str | None = Header(default=None, alias="X-Phase"),  # noqa: B008
    severity: str | None = Query(default=None),  # noqa: B008
) -> JSONResponse:
    try:
        response = await _ingest(
            slug,
            request,
            x_severity=x_severity,
            x_request_id=x_request_id,
            severity=severity,
            x_exit_code=x_exit_code,
            x_duration_ms=x_duration_ms,
            x_phase=x_phase,
        )
    except Problem as exc:
        outcome = {
            404: "not_found",
            429: "rate_limited",
            413: "payload_too_large",
            415: "unsupported_media_type",
            503: "storage_unavailable",
        }.get(exc.status, "error")
        ingestion_requests_total.labels(outcome=outcome).inc()
        raise
    ingestion_requests_total.labels(
        outcome="replay" if response.status_code == 200 else "success"
    ).inc()
    return response


async def _ingest(
    slug: str,
    request: Request,
    *,
    x_severity: str | None,
    x_request_id: str | None,
    severity: str | None,
    x_exit_code: str | None = None,
    x_duration_ms: str | None = None,
    x_phase: str | None = None,
) -> JSONResponse:
    settings = get_settings()
    source_ip = _source_ip(request)

    # 1. Rate limit per IP: primo gate, prima di risolvere lo slug (spec 10.1).
    ip_limit = await check_ip_rate_limit(source_ip)
    if not ip_limit.allowed:
        raise Problem(
            status=429,
            type=PROBLEM_TYPES["rate_limited"],
            title="Too Many Requests",
            detail="Rate limit exceeded for source IP.",
            extra={"retry_after": ip_limit.retry_after},
        )

    # 2. Risoluzione slug -> receiver, sul pool notifyhub_ingest.
    receiver = await resolve_receiver_by_slug(slug)
    if receiver is None:
        raise ingest_not_found()

    if receiver.status != "active":
        redis = await get_redis()
        await redis.incr(f"ingest:rejected:{receiver.id}")
        await redis.expire(f"ingest:rejected:{receiver.id}", 86400)
        raise ingest_not_found()

    # Il tenant sospeso deve rispondere byte-identico al receiver disabilitato
    # (invariante I-2): notifyhub_ingest non ha accesso a tenants, quindi il
    # controllo avviene qui, su una breve transazione app scoped al tenant.
    async with tenant_session(receiver.tenant_id) as session:
        from sqlalchemy import select

        from app.models.tenant import Tenant

        tenant_result = await session.execute(select(Tenant).where(Tenant.id == receiver.tenant_id))
        tenant = tenant_result.scalar_one()
        tenant_suspended = tenant.status == TenantStatus.SUSPENDED

    if tenant_suspended:
        raise ingest_not_found()

    # 3. Rate limit per slug (0 = disattivato, il limite IP resta comunque attivo).
    slug_limit = await check_slug_rate_limit(str(receiver.id), receiver.rate_limit_per_min)
    if not slug_limit.allowed:
        raise Problem(
            status=429,
            type=PROBLEM_TYPES["rate_limited"],
            title="Too Many Requests",
            detail="Rate limit exceeded for this receiver.",
            extra={"retry_after": slug_limit.retry_after},
        )

    _validate_content_type(request.headers.get("content-type"))

    # 4. Limite di dimensione, in streaming: mai piu del cap di sistema, mai piu
    # del cap per-receiver (spec 6.5, 10.1).
    effective_max = min(receiver.max_body_bytes, settings.notifyhub_hard_max_body_bytes)
    raw_body = await _read_body_streaming(request, effective_max)

    # 5. Idempotenza su X-Request-Id (spec 6.3).
    reservation = await reserve(str(receiver.id), x_request_id)
    if reservation.is_replay:
        assert reservation.replay_body is not None
        return JSONResponse(
            status_code=200,
            content=reservation.replay_body,
            headers={"Idempotent-Replay": "true"},
        )
    if reservation.in_progress:
        raise Problem(
            status=409,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="A request with this X-Request-Id is still being processed.",
            extra={"retry_after": 1},
        )

    # 6. Normalizzazione, severity, storage backend, scrittura + outbox nella
    # stessa transazione (spec 8.2).
    try:
        async with tenant_session(receiver.tenant_id) as session:
            # Quota giornaliera e di storage (spec 4.1, enforcement F7): colonne
            # presenti da subito, applicate qui. NULL = illimitata.
            await enforce_tenant_quotas(session, receiver.tenant_id, len(raw_body))

            prepared = await prepare_notification(
                session,
                tenant_id=receiver.tenant_id,
                receiver_id=receiver.id,
                raw_body=raw_body,
                header_severity=x_severity,
                query_severity=severity,
                default_severity=receiver.default_severity,
                exit_code=parse_exit_code(x_exit_code),
                exit_code_severity=receiver.exit_code_severity,
                duration_ms=parse_duration_ms(x_duration_ms),
                duration_threshold_seconds=receiver.duration_threshold_seconds,
                duration_severity=receiver.duration_severity,
                phase=parse_phase(x_phase),
            )

            if prepared.use_object_storage:
                from app.services.storage import upload_object

                assert prepared.storage_key is not None
                try:
                    await upload_object(prepared.storage_key, raw_body)
                except Exception as exc:
                    raise Problem(
                        status=503,
                        type=PROBLEM_TYPES["storage_unavailable"],
                        title="Service Unavailable",
                        detail="Object storage unreachable.",
                    ) from exc

            await persist_notification(
                session,
                tenant_id=receiver.tenant_id,
                receiver_id=receiver.id,
                prepared=prepared,
                source_ip=source_ip,
            )

            from app.services.outbound_resolver import create_deliveries_for_notification
            from app.tasks.enqueue import register_after_commit_enqueue

            delivery_ids = await create_deliveries_for_notification(
                session,
                tenant_id=receiver.tenant_id,
                group_id=receiver.group_id,
                receiver_id=receiver.id,
                notification_id=prepared.id,
                severity=prepared.severity,
            )
            register_after_commit_enqueue(
                session, [(str(did), str(receiver.tenant_id)) for did in delivery_ids]
            )
            forwarded_to = len(delivery_ids)

            body = {
                "id": str(prepared.id),
                "severity": prepared.severity.value,
                "severity_source": prepared.severity_source.value,
                "forwarded_to": forwarded_to,
                "storage_backend": "object" if prepared.use_object_storage else "inline",
            }

        await store_response(str(receiver.id), x_request_id, reservation.owner_token, body)
    except BaseException:
        # Solo il proprietario puo eliminare la sentinella: una richiesta
        # subentrata dopo la scadenza non viene mai cancellata da quella vecchia.
        # Il cleanup e' best effort: un secondo guasto Redis non deve mascherare
        # il Problem originale. shield prova a completarlo anche su cancellazione.
        try:
            await asyncio.shield(release(str(receiver.id), x_request_id, reservation.owner_token))
        except Exception:
            logger.warning("idempotency_release_failed", exc_info=True)
        raise

    return JSONResponse(status_code=201, content=body)
