from pydantic import BaseModel, Field

from app.db.types import RateLimitTier


class RateLimitConfig(BaseModel):
    tier: RateLimitTier
    requests_per_minute: int = Field(ge=1, le=10000)
    requests_per_hour: int = Field(ge=1, le=1000000)
    requests_per_day: int = Field(ge=1, le=10000000)
    burst_size: int = Field(ge=1, le=1000)
    token_refill_rate: float = Field(ge=0.1, le=1000.0)


class RateLimitResponse(BaseModel):
    allowed: bool
    remaining: int
    limit: int
    reset_at: int
    retry_after: int | None = None


class RateLimitStatus(BaseModel):
    tier: RateLimitTier
    requests_used: int
    requests_remaining: int
    reset_at: int
    window_seconds: int


# Default tier configs
TIER_CONFIGS = {
    RateLimitTier.FREE: RateLimitConfig(
        tier=RateLimitTier.FREE,
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000,
        burst_size=2,
        token_refill_rate=0.167,
    ),
    RateLimitTier.BASIC: RateLimitConfig(
        tier=RateLimitTier.BASIC,
        requests_per_minute=100,
        requests_per_hour=5000,
        requests_per_day=50000,
        burst_size=20,
        token_refill_rate=1.67,
    ),
    RateLimitTier.PREMIUM: RateLimitConfig(
        tier=RateLimitTier.PREMIUM,
        requests_per_minute=1000,
        requests_per_hour=50000,
        requests_per_day=500000,
        burst_size=100,
        token_refill_rate=16.7,
    ),
    RateLimitTier.ENTERPRISE: RateLimitConfig(
        tier=RateLimitTier.ENTERPRISE,
        requests_per_minute=10000,
        requests_per_hour=1000000,
        requests_per_day=10000000,
        burst_size=1000,
        token_refill_rate=166.7,
    ),
}
