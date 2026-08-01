import pytest

from app.db.types import RateLimitTier
from app.schemas.ratelimit import TIER_CONFIGS, RateLimitResponse


@pytest.mark.unit
def test_ratelimit_tier_enum():
    assert RateLimitTier.FREE.value == "free"
    assert RateLimitTier.BASIC.value == "basic"
    assert RateLimitTier.PREMIUM.value == "premium"
    assert RateLimitTier.ENTERPRISE.value == "enterprise"


@pytest.mark.unit
def test_free_tier_config():
    config = TIER_CONFIGS[RateLimitTier.FREE]

    assert config.tier == RateLimitTier.FREE
    assert config.requests_per_minute == 10
    assert config.requests_per_hour == 100
    assert config.requests_per_day == 1000
    assert config.burst_size == 2


@pytest.mark.unit
def test_enterprise_tier_config():
    config = TIER_CONFIGS[RateLimitTier.ENTERPRISE]

    assert config.tier == RateLimitTier.ENTERPRISE
    assert config.requests_per_minute == 10000
    assert config.requests_per_hour == 1000000
    assert config.burst_size == 1000


@pytest.mark.unit
def test_ratelimit_response():
    response = RateLimitResponse(
        allowed=True,
        remaining=9,
        limit=10,
        reset_at=1234567890,
        retry_after=None,
    )

    assert response.allowed is True
    assert response.remaining == 9
    assert response.limit == 10
    assert response.retry_after is None


@pytest.mark.unit
def test_ratelimit_response_denied():
    response = RateLimitResponse(
        allowed=False,
        remaining=0,
        limit=10,
        reset_at=1234567890,
        retry_after=5,
    )

    assert response.allowed is False
    assert response.retry_after == 5


@pytest.mark.unit
def test_tier_configs_consistency():
    tiers = [
        RateLimitTier.FREE,
        RateLimitTier.BASIC,
        RateLimitTier.PREMIUM,
        RateLimitTier.ENTERPRISE,
    ]

    for tier in tiers:
        config = TIER_CONFIGS[tier]
        assert config.requests_per_minute >= 1
        assert config.requests_per_hour >= config.requests_per_minute
        assert config.requests_per_day >= config.requests_per_hour
