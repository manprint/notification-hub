"""Object storage MinIO/S3 per i payload oltre INLINE_MAX_BYTES (spec 6.5)."""

import uuid
from datetime import UTC, datetime

import aioboto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
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
    return {
        "endpoint_url": settings.notifyhub_s3_endpoint,
        "aws_access_key_id": settings.notifyhub_s3_access_key,
        "aws_secret_access_key": settings.notifyhub_s3_secret_key,
        "region_name": settings.notifyhub_s3_region,
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


async def delete_object(key: str) -> None:
    settings = get_settings()
    async with _session.client("s3", **_client_kwargs()) as s3:
        await s3.delete_object(Bucket=settings.notifyhub_s3_bucket, Key=key)
