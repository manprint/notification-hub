"""E2E: l'export di audit non tiene una sessione aperta fra un blocco e l'altro (c-be-api-01).

Il download e' lento per costruzione: il client legge un blocco alla volta. Il test
legge il corpo dello StreamingResponse a mano e, a ogni blocco consegnato, conta le
sessioni del tenant ancora aperte. Con una sessione per tutto il download il conteggio
e' 1 a ogni blocco; con una sessione per blocco e' sempre 0.
"""

import uuid
from contextlib import asynccontextmanager

import pytest

from app.core.security import AccessClaims
from app.db.session import tenant_session
from tests.e2e.test_audit import _eventi_marked_read


@pytest.mark.e2e
async def test_export_non_tiene_una_sessione_aperta_durante_il_download(two_tenants, monkeypatch):
    from app.api.v1 import audit as audit_api

    tenant_id, _ = two_tenants
    await _eventi_marked_read(tenant_id, 5)
    monkeypatch.setattr(audit_api, "EXPORT_BATCH_ROWS", 2)

    sessioni_aperte = 0
    sessione_reale = audit_api.tenant_session

    @asynccontextmanager
    async def _sessione_contata(tid: uuid.UUID):  # noqa: ANN202
        nonlocal sessioni_aperte
        sessioni_aperte += 1
        try:
            async with sessione_reale(tid) as sessione:
                yield sessione
        finally:
            sessioni_aperte -= 1

    monkeypatch.setattr(audit_api, "tenant_session", _sessione_contata)
    claims = AccessClaims(
        sub=str(uuid.uuid4()), tid=str(tenant_id), role="owner", exp=0, iat=0, jti="test"
    )

    # La sessione della richiesta e' quella che `db` fornirebbe: legge il conteggio.
    async with tenant_session(tenant_id) as richiesta:
        risposta = await audit_api.export_audit_events(
            format="json",
            notification_status_only=False,
            notification_id=None,
            actor_user_id=None,
            action="notification.marked_read",
            resource_type=None,
            resource_id=None,
            outcome=None,
            from_=None,
            to=None,
            claims=claims,
            session=richiesta,
        )

        sessioni_ai_blocchi: list[int] = []
        byte_ricevuti = 0
        async for blocco in risposta.body_iterator:
            # Il generatore e' fermo sul suo `yield`: qui il conteggio dice cosa resta
            # aperto mentre il client elabora il blocco.
            sessioni_ai_blocchi.append(sessioni_aperte)
            byte_ricevuti += len(blocco)

    assert byte_ricevuti > 0
    assert len(sessioni_ai_blocchi) >= 3
    assert sessioni_ai_blocchi == [0] * len(sessioni_ai_blocchi)
