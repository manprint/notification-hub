import time
from dataclasses import dataclass

from app.core.redis import get_redis


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


async def sliding_window_hit(key: str, limit: int, window_seconds: int) -> RateLimitResult:
    if limit <= 0:
        return RateLimitResult(allowed=True, remaining=-1, retry_after=0)

    redis = await get_redis()
    now = int(time.time() * 1000)
    window_start = now - (window_seconds * 1000)

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zcard(key)
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, window_seconds)
    results = await pipe.execute()

    count_before = results[1]
    if count_before >= limit:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        if oldest:
            oldest_score = int(oldest[0][1])
            retry_after = (oldest_score + (window_seconds * 1000) - now) // 1000
            return RateLimitResult(allowed=False, remaining=0, retry_after=max(1, retry_after))

    remaining = max(0, limit - count_before - 1)
    return RateLimitResult(allowed=True, remaining=remaining, retry_after=0)
