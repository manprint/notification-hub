"""Il client Redis ha timeout di socket: un server che tace non blocca per sempre."""

import asyncio

import pytest
import redis.exceptions

from app.core import redis as redis_module
from app.core.config import get_settings


@pytest.mark.unit
@pytest.mark.asyncio
async def test_redis_che_tace_fa_scattare_il_timeout_invece_di_restare_appeso(monkeypatch):
    async def _server_muto(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # Accetta la connessione e non risponde mai: il caso del Redis in pausa.
        await reader.read()
        writer.close()

    server = await asyncio.start_server(_server_muto, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    settings = get_settings().model_copy(
        update={
            "redis_url": f"redis://127.0.0.1:{port}/0",
            "redis_socket_timeout_seconds": 0.3,
        }
    )
    monkeypatch.setattr(redis_module, "get_settings", lambda: settings)
    monkeypatch.setattr(redis_module, "_redis_client", None)

    client = await redis_module.get_redis()
    try:
        with pytest.raises(redis.exceptions.TimeoutError):
            await asyncio.wait_for(client.get("chiave"), timeout=5)
    finally:
        await client.aclose()
        server.close()
        await server.wait_closed()
