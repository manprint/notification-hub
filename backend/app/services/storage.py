import uuid

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def should_use_object_storage(body_length: int) -> bool:
    """Determine if notification body should be stored in object storage."""
    settings = get_settings()
    threshold = settings.notifyhub_hard_max_body_bytes // 2
    return body_length > threshold


async def upload_notification_body(notification_id: uuid.UUID, body: str) -> str:
    """Upload notification body to S3, return object key."""
    settings = get_settings()
    key = f"notifications/{notification_id}/body.txt"

    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.notifyhub_s3_endpoint,
            aws_access_key_id=settings.notifyhub_s3_access_key,
            aws_secret_access_key=settings.notifyhub_s3_secret_key,
            region_name=settings.notifyhub_s3_region,
        )

        s3_client.put_object(
            Bucket=settings.notifyhub_s3_bucket,
            Key=key,
            Body=body.encode(),
            ContentType="text/plain",
        )

        logger.info("notification_uploaded_to_s3", notification_id=notification_id, key=key)
        return key
    except ClientError as e:
        logger.error("s3_upload_failed", notification_id=notification_id, error=str(e))
        raise


async def fetch_notification_body(storage_key: str) -> str:
    """Fetch notification body from S3."""
    settings = get_settings()

    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.notifyhub_s3_endpoint,
            aws_access_key_id=settings.notifyhub_s3_access_key,
            aws_secret_access_key=settings.notifyhub_s3_secret_key,
            region_name=settings.notifyhub_s3_region,
        )

        response = s3_client.get_object(Bucket=settings.notifyhub_s3_bucket, Key=storage_key)
        body = response["Body"].read().decode()
        return body
    except ClientError as e:
        logger.error("s3_fetch_failed", storage_key=storage_key, error=str(e))
        raise


def calculate_retry_delay(attempt_number: int) -> int:
    """Calculate exponential backoff delay in seconds.

    Attempt 1: 2^1 = 2s
    Attempt 2: 2^2 = 4s
    Attempt 3: 2^3 = 8s
    Attempt 4: 2^4 = 16s
    Attempt 5: 2^5 = 32s (max 5 attempts)
    """
    max_attempt = 5
    if attempt_number > max_attempt:
        return 0
    return 2 ** min(attempt_number, max_attempt)
