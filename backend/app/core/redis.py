from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

_redis_client: Any = None


async def get_redis() -> Any:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client
