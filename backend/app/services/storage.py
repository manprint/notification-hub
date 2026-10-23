"""Object storage MinIO/S3 per i payload oltre INLINE_MAX_BYTES (spec 6.5)."""

import uuid
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from datetime import UTC, datetime

import aioboto3
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings, s3_timeouts
from app.core.logging import get_logger

logger = get_logger(__name__)

_session = aioboto3.Session()


def should_use_object_storage(body_length: int) -> bool:
    """Sopra INLINE_MAX_BYTES (default 1MB) il corpo va offloaded su MinIO."""
    settings = get_settings()
    return body_length > settings.notifyhub_inline_max_bytes


def object_key(tenant_id: uuid.UUID, notification_id: uuid.UUID) -> str:
    """{tenant_id}/{yyyy}/{mm}/{dd}/{notification_id}.txt (spec 6.5).

    Il prefisso per tenant rende banale sia il purge per tenant sia un'eventuale
    lifecycle policy, senza moltiplicare i bucket.
    """
    now = datetime.now(UTC)
    return f"{tenant_id}/{now:%Y}/{now:%m}/{now:%d}/{notification_id}.txt"


def _client_kwargs() -> dict:
    settings = get_settings()
    # Timeout espliciti: senza, botocore aspetta 60 s per tentativo e un MinIO
    # bloccato tiene occupata la richiesta ben oltre il timeout del pool.
    return {
        "endpoint_url": settings.notifyhub_s3_endpoint,
        "aws_access_key_id": settings.notifyhub_s3_access_key,
        "aws_secret_access_key": settings.notifyhub_s3_secret_key,
        "region_name": settings.notifyhub_s3_region,
        "config": AioConfig(**s3_timeouts(settings)),
    }


async def upload_object(key: str, body: bytes) -> None:
    """PUT su MinIO. Deve avvenire PRIMA del commit Postgres (spec 6.5):
    il chiamante e responsabile dell'ordine, questa funzione solleva soltanto."""
    settings = get_settings()
    try:
        async with _session.client("s3", **_client_kwargs()) as s3:
            await s3.put_object(
                Bucket=settings.notifyhub_s3_bucket,
                Key=key,
                Body=body,
                ContentType="text/plain",
            )
        logger.info("object_uploaded", key=key, size=len(body))
    except ClientError as e:
        logger.error("object_upload_failed", key=key, error=str(e))
        raise


async def fetch_object(key: str) -> bytes:
    settings = get_settings()
    async with _session.client("s3", **_client_kwargs()) as s3:
        response = await s3.get_object(Bucket=settings.notifyhub_s3_bucket, Key=key)
        async with response["Body"] as stream:
            return await stream.read()


async def stream_object(key: str) -> tuple[int, AsyncIterator[bytes]]:
    """Lunghezza e blocchi dell'oggetto, senza caricarlo in memoria (spec 9.5).

    La richiesta a MinIO parte qui, prima che la risposta inizi: una chiave
    mancante e' un errore e non un 200 con corpo troncato. Il client e il corpo
    si chiudono quando i blocchi finiscono o il chiamante smette di leggerli.
    """
    settings = get_settings()
    stack = AsyncExitStack()
    try:
        s3 = await stack.enter_async_context(_session.client("s3", **_client_kwargs()))
        response = await s3.get_object(Bucket=settings.notifyhub_s3_bucket, Key=key)
        corpo = response["Body"]
        await stack.enter_async_context(corpo)
    except BaseException:
        await stack.aclose()
        raise

    async def _blocchi() -> AsyncIterator[bytes]:
        try:
            async for blocco in corpo.iter_chunks():
                yield blocco
        finally:
            await stack.aclose()

    return int(response["ContentLength"]), _blocchi()


async def delete_object(key: str) -> None:
    settings = get_settings()
    async with _session.client("s3", **_client_kwargs()) as s3:
        await s3.delete_object(Bucket=settings.notifyhub_s3_bucket, Key=key)
