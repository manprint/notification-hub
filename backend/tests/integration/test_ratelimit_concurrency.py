import asyncio
import uuid

import pytest

from app.core.redis import get_redis
from app.services.ratelimit import sliding_window_hit


@pytest.mark.integration
async def test_sliding_window_e_atomica_sotto_concorrenza():
    key = f"test:ratelimit:concurrent:{uuid.uuid4()}"
    redis = await get_redis()
    try:
        results = await asyncio.gather(
            *(sliding_window_hit(key, limit=5, window_seconds=60) for _ in range(30))
        )
        assert sum(result.allowed for result in results) == 5
        assert await redis.zcard(key) == 5
    finally:
        await redis.delete(key)


@pytest.mark.integration
async def test_retry_after_arrotonda_per_eccesso(monkeypatch):
    key = f"test:ratelimit:retry-after:{uuid.uuid4()}"
    redis = await get_redis()
    try:
        monkeypatch.setattr("app.services.ratelimit.time.time", lambda: 1_000.1)
        assert (await sliding_window_hit(key, limit=1, window_seconds=2)).allowed is True

        monkeypatch.setattr("app.services.ratelimit.time.time", lambda: 1_000.2)
        blocked = await sliding_window_hit(key, limit=1, window_seconds=2)
        assert blocked.allowed is False
        assert blocked.retry_after == 2
    finally:
        await redis.delete(key)
