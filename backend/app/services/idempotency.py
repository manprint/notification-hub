"""Idempotenza dell'ingestion su X-Request-Id (spec 6.3)."""

import json
from dataclasses import dataclass
from hashlib import sha256

from app.core.redis import get_redis

IDEMPOTENCY_WINDOW_SECONDS = 300
_PROCESSING_SENTINEL = "__processing__"


def _idempotency_key(receiver_id: str, request_id: str) -> str:
    digest = sha256(request_id.encode()).hexdigest()
    return f"ingest:idem:{receiver_id}:{digest}"


@dataclass
class IdempotencyReservation:
    is_replay: bool
    replay_body: dict | None = None


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

    was_set = await redis.set(key, _PROCESSING_SENTINEL, nx=True, ex=IDEMPOTENCY_WINDOW_SECONDS)
    if was_set:
        return IdempotencyReservation(is_replay=False)

    stored = await redis.get(key)
    if stored is None or stored == _PROCESSING_SENTINEL:
        # Race fra due richieste concorrenti con lo stesso X-Request-Id: la prima
        # non ha ancora scritto la risposta finale. Trattarla come non deduplicata
        # e la scelta piu semplice che non perde la richiesta; resta un caso raro
        # (stesso ID, stesso istante), non il retry di rete che la spec copre.
        return IdempotencyReservation(is_replay=False)

    return IdempotencyReservation(is_replay=True, replay_body=json.loads(stored))


async def store_response(receiver_id: str, request_id: str | None, body: dict) -> None:
    if not request_id:
        return
    redis = await get_redis()
    key = _idempotency_key(receiver_id, request_id)
    await redis.set(key, json.dumps(body), ex=IDEMPOTENCY_WINDOW_SECONDS)
