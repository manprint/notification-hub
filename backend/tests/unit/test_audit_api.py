"""Forma SQL del filtro per notifica dell'audit: l'indice GIN della migrazione
0016 serve solo l'espressione `(context -> 'notification_ids')`, non la forma a
sottoscrizione che SQLAlchemy genera di default."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.audit import _notification_event_ids


def _sql(statement: Any) -> str:
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


@pytest.mark.unit
def test_il_ramo_del_bulk_read_usa_l_espressione_indicizzata() -> None:
    notification_id = uuid.uuid4()
    sql = _sql(_notification_event_ids(SimpleNamespace(tid=str(uuid.uuid4())), notification_id))

    expected = (
        f"(audit_events.context -> 'notification_ids') @> jsonb_build_array('{notification_id}')"
    )
    assert expected in sql
    assert "context['notification_ids']" not in sql


@pytest.mark.unit
def test_il_ramo_della_patch_singola_e_limitato_alle_notifiche() -> None:
    """Un evento di un'altra risorsa con lo stesso uuid non deve entrare."""
    notification_id = uuid.uuid4()
    sql = _sql(_notification_event_ids(SimpleNamespace(tid=str(uuid.uuid4())), notification_id))

    assert "audit_events.resource_type = 'notification'" in sql
    assert "WITH notification_events AS MATERIALIZED" in sql
