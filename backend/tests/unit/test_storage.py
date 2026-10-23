import uuid
from contextlib import asynccontextmanager

import pytest
from botocore.exceptions import ClientError

from app.services import storage
from app.services.storage import object_key, should_use_object_storage, stream_object


class _Corpo:
    """Stand-in dello StreamingBody di aiobotocore: context manager asincrono a blocchi.
    Come nel vero StreamingBody, __aenter__ non restituisce il corpo ma la risposta
    interna, priva di iter_chunks."""

    def __init__(self, blocchi: list[bytes]) -> None:
        self._blocchi = blocchi
        self.chiuso = False

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *exc: object) -> None:
        self.chiuso = True

    async def iter_chunks(self):  # type: ignore[no-untyped-def]
        for blocco in self._blocchi:
            yield blocco


class _S3:
    def __init__(self, risposta: dict | Exception) -> None:
        self._risposta = risposta
        self.chiesti: list[str] = []

    async def get_object(self, **kwargs: str) -> dict:
        self.chiesti.append(kwargs["Key"])
        if isinstance(self._risposta, Exception):
            raise self._risposta
        return self._risposta


def _finto_client(monkeypatch, s3: _S3, stato: dict):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def client(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            yield s3
        finally:
            stato["client_chiuso"] = True

    monkeypatch.setattr(storage._session, "client", client)


@pytest.mark.unit
def test_should_use_object_storage_small_body():
    small_body = "x" * 1000
    assert not should_use_object_storage(len(small_body.encode()))


@pytest.mark.unit
def test_should_use_object_storage_boundary():
    threshold = 1048576
    assert not should_use_object_storage(threshold)
    assert should_use_object_storage(threshold + 1)


@pytest.mark.unit
def test_should_use_object_storage_large_body():
    large_body = "x" * 2_000_000
    assert should_use_object_storage(len(large_body.encode()))


@pytest.mark.unit
def test_object_key_has_tenant_prefix_and_date_partitioning():
    tenant_id = uuid.uuid4()
    notification_id = uuid.uuid4()

    key = object_key(tenant_id, notification_id)

    parts = key.split("/")
    assert parts[0] == str(tenant_id)
    assert len(parts) == 5
    assert parts[4] == f"{notification_id}.txt"


@pytest.mark.unit
async def test_stream_object_consegna_i_blocchi_uno_per_volta_e_chiude_tutto(monkeypatch):
    corpo = _Corpo([b"uno", b"due", b"tre"])
    s3 = _S3({"Body": corpo, "ContentLength": 9})
    stato: dict = {}
    _finto_client(monkeypatch, s3, stato)

    lunghezza, blocchi = await stream_object("tenant/2026/10/23/abc.txt")

    assert lunghezza == 9
    assert s3.chiesti == ["tenant/2026/10/23/abc.txt"]
    assert not corpo.chiuso
    ricevuti = [blocco async for blocco in blocchi]
    assert ricevuti == [b"uno", b"due", b"tre"]
    assert corpo.chiuso
    assert stato["client_chiuso"]


@pytest.mark.unit
async def test_stream_object_chiude_il_client_se_il_chiamante_smette_di_leggere(monkeypatch):
    corpo = _Corpo([b"uno", b"due", b"tre"])
    s3 = _S3({"Body": corpo, "ContentLength": 9})
    stato: dict = {}
    _finto_client(monkeypatch, s3, stato)

    _, blocchi = await stream_object("chiave")
    assert await anext(blocchi) == b"uno"
    await blocchi.aclose()

    assert corpo.chiuso
    assert stato["client_chiuso"]


@pytest.mark.unit
async def test_stream_object_chiave_mancante_solleva_prima_dei_blocchi(monkeypatch):
    errore = ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
    s3 = _S3(errore)
    stato: dict = {}
    _finto_client(monkeypatch, s3, stato)

    with pytest.raises(ClientError):
        await stream_object("chiave-inesistente")

    assert stato["client_chiuso"]
