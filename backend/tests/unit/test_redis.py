import pytest

from app.core.redis import get_redis


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_redis_singleton():
    redis1 = await get_redis()
    redis2 = await get_redis()
    assert redis1 is redis2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_redis_returns_object():
    redis = await get_redis()
    assert redis is not None
    assert hasattr(redis, "pipeline")
    assert hasattr(redis, "get")
    assert hasattr(redis, "set")
    assert hasattr(redis, "zadd")
    assert hasattr(redis, "zrange")
