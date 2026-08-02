"""Rate limiting su Redis, sliding window (spec 10.1)."""

import time
import uuid
from dataclasses import dataclass

from app.core.redis import get_redis


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


async def sliding_window_hit(key: str, limit: int, window_seconds: int) -> RateLimitResult:
    """Sliding window log su un sorted set Redis.

    `limit <= 0` disattiva il limite (usato da receivers.rate_limit_per_min = 0,
    spec 4.2 e 10.1: disattiva solo il limite per-slug, non quello per IP).

    Una richiesta bloccata NON viene aggiunta al set: contarla sposterebbe in
    avanti la scadenza del blocco a ogni tentativo, impedendo al limite di
    riaprirsi mai sotto pressione sostenuta (vedi docs/REVIEW.md S6).
    """
    if limit <= 0:
        return RateLimitResult(allowed=True, remaining=-1, retry_after=0)

    redis = await get_redis()
    now_ms = int(time.time() * 1000)
    window_start_ms = now_ms - (window_seconds * 1000)

    await redis.zremrangebyscore(key, 0, window_start_ms)
    count = await redis.zcard(key)

    if count >= limit:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        if oldest:
            oldest_score = int(oldest[0][1])
            retry_after = (oldest_score + (window_seconds * 1000) - now_ms) // 1000
        else:
            retry_after = window_seconds
        return RateLimitResult(allowed=False, remaining=0, retry_after=max(1, retry_after))

    member = f"{now_ms}:{uuid.uuid4()}"
    await redis.zadd(key, {member: now_ms})
    await redis.expire(key, window_seconds)

    remaining = max(0, limit - count - 1)
    return RateLimitResult(allowed=True, remaining=remaining, retry_after=0)


IP_RATE_LIMIT_PER_MINUTE = 300


async def check_ip_rate_limit(source_ip: str) -> RateLimitResult:
    """Primo gate dell'ingestion (spec 10.1): valutato PRIMA di risolvere lo slug,
    cosi uno scan di slug inesistenti non genera nemmeno una query."""
    return await sliding_window_hit(
        f"ingest:ratelimit:ip:{source_ip}", IP_RATE_LIMIT_PER_MINUTE, 60
    )


async def check_slug_rate_limit(receiver_id: str, rate_limit_per_min: int) -> RateLimitResult:
    return await sliding_window_hit(f"ingest:ratelimit:slug:{receiver_id}", rate_limit_per_min, 60)
