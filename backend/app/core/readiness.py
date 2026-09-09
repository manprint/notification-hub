"""GET /readyz: Postgres + Redis + MinIO HeadBucket (spec 13)."""

import aioboto3
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.session import engine_app

logger = get_logger(__name__)


async def _check_postgres() -> bool:
    try:
        async with engine_app.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("readyz_postgres_unreachable")
        return False


async def _check_redis() -> bool:
    try:
        redis = await get_redis()
        return bool(await redis.ping())
    except Exception:
        logger.warning("readyz_redis_unreachable")
        return False


async def _check_minio() -> bool:
    settings = get_settings()
    session = aioboto3.Session()
    try:
        async with session.client(
            "s3",
            endpoint_url=settings.notifyhub_s3_endpoint,
            aws_access_key_id=settings.notifyhub_s3_access_key,
            aws_secret_access_key=settings.notifyhub_s3_secret_key,
            region_name=settings.notifyhub_s3_region,
        ) as s3:
            await s3.head_bucket(Bucket=settings.notifyhub_s3_bucket)
        return True
    except Exception:
        logger.warning("readyz_minio_unreachable")
        return False


async def check_readiness() -> dict[str, bool]:
    return {
        "postgres": await _check_postgres(),
        "redis": await _check_redis(),
        "minio": await _check_minio(),
    }
