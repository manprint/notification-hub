import pytest

from app.services.ratelimit import RateLimitResult, sliding_window_hit


@pytest.mark.unit
def test_rate_limit_result_allowed():
    result = RateLimitResult(allowed=True, remaining=5, retry_after=0)
    assert result.allowed is True
    assert result.remaining == 5
    assert result.retry_after == 0


@pytest.mark.unit
def test_rate_limit_result_blocked():
    result = RateLimitResult(allowed=False, remaining=0, retry_after=30)
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after == 30


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sliding_window_zero_limit():
    result = await sliding_window_hit("test_key", 0, 60)
    assert result.allowed is True
    assert result.remaining == -1
    assert result.retry_after == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sliding_window_negative_limit():
    result = await sliding_window_hit("test_key", -1, 60)
    assert result.allowed is True
    assert result.remaining == -1
