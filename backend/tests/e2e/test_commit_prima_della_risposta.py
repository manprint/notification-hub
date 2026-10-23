"""E2E: il commit della transazione avviene prima che la risposta parta.

Una dipendenza con yield di scope "request" (il default) esce dopo l'invio della
risposta. `db` fa il commit nella sua uscita: un errore del commit (vincolo
differito, unicita al flush finale) arrivava al client come 2xx gia inviato, e
l'handler 409 non poteva piu girare. Con scope "function" il commit avviene
dentro la richiesta, prima dell'invio.

Il test parla ASGI grezzo e non httpx: ASGITransport rilancia l'eccezione e non
mostra l'ordine dei messaggi, che e' esattamente cio' che conta qui.
"""

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import tenant_session
from app.main import create_app
from app.models.group import Group


@pytest.fixture
def commit_spiato(monkeypatch):
    """Registra ogni commit e, su richiesta del test, lo fa fallire.

    Il fallimento simula un errore del commit che l'endpoint non vede: la route fa
    solo flush, come una scrittura che non viola vincoli al momento dell'INSERT.
    """
    stato: dict = {"eventi": [], "fallisci": False}
    originale = AsyncSession.commit

    async def commit_spia(self: AsyncSession) -> None:
        stato["eventi"].append("commit")
        if stato["fallisci"]:
            raise IntegrityError("COMMIT", {}, Exception("vincolo differito violato"))
        await originale(self)

    monkeypatch.setattr(AsyncSession, "commit", commit_spia)
    return stato


async def _richiesta_asgi(
    app, metodo: str, percorso: str, token: str, corpo: dict, eventi: list[str]
) -> None:
    """Esegue la richiesta ASGI e accoda in `eventi` lo stato inviato al client.

    Un'eccezione sollevata dopo l'invio della risposta resta visibile come
    "errore", senza nascondere lo status gia mandato.
    """
    payload = json.dumps(corpo).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": metodo,
        "scheme": "http",
        "path": percorso,
        "raw_path": percorso.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", b"application/json"),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    letto = False

    async def receive() -> dict:
        nonlocal letto
        if letto:
            return {"type": "http.disconnect"}
        letto = True
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(messaggio: dict) -> None:
        if messaggio["type"] == "http.response.start":
            eventi.append(f"start:{messaggio['status']}")

    try:
        await app(scope, receive, send)
    except Exception:
        eventi.append("errore")


@pytest.mark.e2e
async def test_errore_del_commit_non_diventa_un_successo(
    commit_spiato, api_client, owner_token, two_tenants
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    nome = f"commit-fallito-{uuid.uuid4().hex[:8]}"
    commit_spiato["fallisci"] = True
    commit_spiato["eventi"].clear()

    eventi = commit_spiato["eventi"]
    await _richiesta_asgi(create_app(), "POST", "/api/v1/groups", token, {"name": nome}, eventi)

    # Il commit fallisce prima dell'invio: il client riceve il 409, non un 201 seguito
    # da un errore muto.
    assert eventi == ["commit", "start:409"]
    commit_spiato["fallisci"] = False
    async with tenant_session(tenant_id) as session:
        gruppi = await session.execute(select(Group).where(Group.name == nome))
        assert gruppi.scalars().all() == []


@pytest.mark.e2e
async def test_commit_avviene_prima_dell_invio_della_risposta(
    commit_spiato, api_client, owner_token, two_tenants
):
    tenant_id, _ = two_tenants
    token = await owner_token(api_client, tenant_id)
    commit_spiato["eventi"].clear()

    eventi = commit_spiato["eventi"]
    await _richiesta_asgi(
        create_app(),
        "POST",
        "/api/v1/groups",
        token,
        {"name": f"commit-ordine-{uuid.uuid4().hex[:8]}"},
        eventi,
    )

    assert eventi == ["commit", "start:201"]
