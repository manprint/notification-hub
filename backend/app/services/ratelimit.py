"""Rate limiting su Redis, sliding window (spec 10.1)."""

import time
import uuid
from dataclasses import dataclass

from app.core.redis import get_redis

_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local window_start_ms = tonumber(ARGV[1])
local now_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local window_seconds = tonumber(ARGV[4])
local member = ARGV[5]

redis.call("ZREMRANGEBYSCORE", key, "-inf", window_start_ms)
local count = redis.call("ZCARD", key)

if count >= limit then
    local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
    local retry_after = window_seconds
    if #oldest >= 2 then
        retry_after = math.ceil(
            (tonumber(oldest[2]) + (window_seconds * 1000) - now_ms) / 1000
        )
        if retry_after < 1 then
            retry_after = 1
        end
    end
    return {0, 0, retry_after}
end

redis.call("ZADD", key, now_ms, member)
redis.call("EXPIRE", key, window_seconds)
return {1, limit - count - 1, 0}
"""


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
    member = f"{now_ms}:{uuid.uuid4()}"
    allowed, remaining, retry_after = await redis.eval(
        _SLIDING_WINDOW_SCRIPT,
        1,
        key,
        now_ms - (window_seconds * 1000),
        now_ms,
        limit,
        window_seconds,
        member,
    )
    return RateLimitResult(
        allowed=bool(allowed),
        remaining=int(remaining),
        retry_after=int(retry_after),
    )


IP_RATE_LIMIT_PER_MINUTE = 300


async def check_ip_rate_limit(source_ip: str) -> RateLimitResult:
    """Primo gate dell'ingestion (spec 10.1): valutato PRIMA di risolvere lo slug,
    cosi uno scan di slug inesistenti non genera nemmeno una query."""
    return await sliding_window_hit(
        f"ingest:ratelimit:ip:{source_ip}", IP_RATE_LIMIT_PER_MINUTE, 60
    )


async def check_slug_rate_limit(receiver_id: str, rate_limit_per_min: int) -> RateLimitResult:
    return await sliding_window_hit(f"ingest:ratelimit:slug:{receiver_id}", rate_limit_per_min, 60)
