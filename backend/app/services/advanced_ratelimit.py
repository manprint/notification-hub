import time
from dataclasses import dataclass

import aioredis

from app.db.types import RateLimitTier
from app.schemas.ratelimit import TIER_CONFIGS, RateLimitResponse


@dataclass
class TokenBucketState:
    """Token bucket algorithm state."""

    tokens: float
    last_refill: float
    capacity: float
    refill_rate: float


class AdvancedRateLimiter:
    """Token bucket rate limiter with tier support."""

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def check_limit(
        self,
        key: str,
        tier: RateLimitTier = RateLimitTier.FREE,
        cost: int = 1,
    ) -> RateLimitResponse:
        """Check if request is allowed under rate limit."""
        config = TIER_CONFIGS[tier]

        state_key = f"ratelimit:state:{key}"

        now = time.time()

        state_str = await self.redis.get(state_key)
        if state_str:
            parts = state_str.decode().split(":")
            state = TokenBucketState(
                tokens=float(parts[0]),
                last_refill=float(parts[1]),
                capacity=float(parts[2]),
                refill_rate=float(parts[3]),
            )
        else:
            state = TokenBucketState(
                tokens=float(config.burst_size),
                last_refill=now,
                capacity=float(config.burst_size),
                refill_rate=config.token_refill_rate,
            )

        elapsed = now - state.last_refill
        new_tokens = min(
            state.capacity,
            state.tokens + (elapsed * state.refill_rate),
        )

        allowed = new_tokens >= cost
        remaining = int(max(0, new_tokens - cost))

        new_state = TokenBucketState(
            tokens=new_tokens - cost if allowed else new_tokens,
            last_refill=now,
            capacity=state.capacity,
            refill_rate=state.refill_rate,
        )

        state_str = (
            f"{new_state.tokens}:{new_state.last_refill}:"
            f"{new_state.capacity}:{new_state.refill_rate}"
        )
        await self.redis.setex(state_key, 86400, state_str)

        reset_at = int(now + 60)
        retry_after = int((cost - new_tokens) / state.refill_rate) if not allowed else None

        return RateLimitResponse(
            allowed=allowed,
            remaining=remaining,
            limit=config.burst_size,
            reset_at=reset_at,
            retry_after=retry_after,
        )

    async def get_status(
        self,
        key: str,
        tier: RateLimitTier = RateLimitTier.FREE,
    ) -> dict:
        """Get current rate limit status."""
        config = TIER_CONFIGS[tier]
        state_key = f"ratelimit:state:{key}"

        state_str = await self.redis.get(state_key)
        if state_str:
            parts = state_str.decode().split(":")
            tokens = float(parts[0])
        else:
            tokens = float(config.burst_size)

        now = int(time.time())
        reset_at = now + 60

        return {
            "tier": tier.value,
            "tokens": int(tokens),
            "capacity": config.burst_size,
            "reset_at": reset_at,
            "limits": {
                "per_minute": config.requests_per_minute,
                "per_hour": config.requests_per_hour,
                "per_day": config.requests_per_day,
            },
        }
