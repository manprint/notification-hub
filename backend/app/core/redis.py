from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

_redis_client: Any = None


async def get_redis() -> Any:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        # Timeout espliciti: di default redis-py non ne ha, e un Redis che tace con
        # la connessione aperta bloccherebbe ogni ingestion su rate limit e idempotenza.
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_connect_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
            health_check_interval=30,
        )
    return _redis_client
