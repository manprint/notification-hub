"""Idempotenza dell'ingestion su X-Request-Id (spec 6.3)."""

import asyncio
import json
import secrets
from dataclasses import dataclass
from hashlib import sha256

from app.core.redis import get_redis

IDEMPOTENCY_WINDOW_SECONDS = 300
IDEMPOTENCY_WAIT_SECONDS = 5.0
IDEMPOTENCY_POLL_SECONDS = 0.05
_PROCESSING_PREFIX = "__processing__:"

_COMPARE_AND_DELETE = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""

_COMPARE_AND_STORE = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    redis.call("SET", KEYS[1], ARGV[2], "EX", ARGV[3])
    return 1
end
return 0
"""


def _idempotency_key(receiver_id: str, request_id: str) -> str:
    digest = sha256(request_id.encode()).hexdigest()
    return f"ingest:idem:{receiver_id}:{digest}"


@dataclass
class IdempotencyReservation:
    is_replay: bool
    replay_body: dict | None = None
    owner_token: str | None = None
    in_progress: bool = False


async def reserve(receiver_id: str, request_id: str | None) -> IdempotencyReservation:
    """Riserva la chiave per la prima occorrenza, o segnala un replay.

    Header assente -> nessuna deduplica: comportamento identico a non passarlo.
    Prima occorrenza -> la chiave viene scritta con SET NX EX 300, si procede con
    l'ingestion normale e la risposta finale va salvata con `store_response`.
    Occorrenza ripetuta entro la finestra -> il corpo gia salvato viene restituito
    cosi com'era per la 201 originale, con status 200 e Idempotent-Replay: true.
    """
    if not request_id:
        return IdempotencyReservation(is_replay=False)

    redis = await get_redis()
    key = _idempotency_key(receiver_id, request_id)

    owner_token = secrets.token_urlsafe(16)
    sentinel = f"{_PROCESSING_PREFIX}{owner_token}"
    was_set = await redis.set(key, sentinel, nx=True, ex=IDEMPOTENCY_WINDOW_SECONDS)
    if was_set:
        return IdempotencyReservation(is_replay=False, owner_token=owner_token)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + IDEMPOTENCY_WAIT_SECONDS
    while True:
        stored = await redis.get(key)
        if stored is None:
            # Il proprietario ha fallito e ha rilasciato la prenotazione: prova
            # a subentrare senza aprire una finestra per due proprietari.
            was_set = await redis.set(key, sentinel, nx=True, ex=IDEMPOTENCY_WINDOW_SECONDS)
            if was_set:
                return IdempotencyReservation(is_replay=False, owner_token=owner_token)
        elif not stored.startswith(_PROCESSING_PREFIX):
            return IdempotencyReservation(is_replay=True, replay_body=json.loads(stored))

        if loop.time() >= deadline:
            return IdempotencyReservation(is_replay=False, in_progress=True)
        await asyncio.sleep(IDEMPOTENCY_POLL_SECONDS)


async def store_response(
    receiver_id: str,
    request_id: str | None,
    owner_token: str | None,
    body: dict,
) -> None:
    if not request_id or owner_token is None:
        return
    redis = await get_redis()
    key = _idempotency_key(receiver_id, request_id)
    await redis.eval(
        _COMPARE_AND_STORE,
        1,
        key,
        f"{_PROCESSING_PREFIX}{owner_token}",
        json.dumps(body),
        IDEMPOTENCY_WINDOW_SECONDS,
    )


async def release(receiver_id: str, request_id: str | None, owner_token: str | None) -> None:
    if not request_id or owner_token is None:
        return
    redis = await get_redis()
    key = _idempotency_key(receiver_id, request_id)
    await redis.eval(
        _COMPARE_AND_DELETE,
        1,
        key,
        f"{_PROCESSING_PREFIX}{owner_token}",
    )
