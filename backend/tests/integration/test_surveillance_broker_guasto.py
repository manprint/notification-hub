"""Job di sorveglianza con il broker che rifiuta gli accodamenti (c-be-infra-01).

La transazione di ogni tenant e' gia committata quando si accoda. Se il broker
solleva, l'errore non deve uscire dal job: i tenant successivi di quel giro vanno
comunque valutati, altrimenti la loro assenza resta non registrata fino al giro dopo.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.types import Severity
from app.tasks.enqueue import reset_enqueue_function, set_enqueue_function
from app.tasks.maintenance import check_expected_schedules
from tests.conftest_factories import create_receiver
from tests.integration.test_surveillance_job import (
    _canale_con_soglia,
    _notifiche,
    _receiver,
    _sorveglia,
)


@pytest.mark.integration
async def test_broker_che_rifiuta_gli_accodamenti_non_ferma_i_tenant_successivi(two_tenants):
    tenant_a, tenant_b = two_tenants
    receiver_a = await create_receiver(tenant_a, uuid.uuid4().hex[:22])
    receiver_b = await create_receiver(tenant_b, uuid.uuid4().hex[:22])
    for tenant_id, receiver_id in ((tenant_a, receiver_a), (tenant_b, receiver_b)):
        await _sorveglia(
            tenant_id,
            receiver_id,
            last_notification_at=datetime.now(UTC) - timedelta(days=2),
        )
        # Senza un canale il job non crea consegne, quindi non accoda niente.
        gruppo = (await _receiver(tenant_id, receiver_id)).group_id
        await _canale_con_soglia(tenant_id, gruppo, Severity.INFO)

    tentativi: list[str] = []

    def _broker_che_rifiuta(delivery_id: str, tid: str) -> None:
        tentativi.append(tid)
        raise ConnectionError("broker non raggiungibile")

    set_enqueue_function(_broker_che_rifiuta)
    try:
        # Il job non deve sollevare: l'errore del broker e' un fatto da registrare.
        check_expected_schedules()
    finally:
        reset_enqueue_function()

    assert len(tentativi) >= 2
    assert len(await _notifiche(tenant_a, receiver_a)) == 1
    assert len(await _notifiche(tenant_b, receiver_b)) == 1
