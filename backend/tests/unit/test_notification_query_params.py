"""Validazione dei parametri di ricerca e di periodo condivisi da notifiche e audit."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.notification import BulkReadIn, as_utc


@pytest.mark.unit
def test_un_istante_senza_fuso_e_utc_e_non_l_ora_locale() -> None:
    value = as_utc(datetime(2026, 10, 1, 0, 0))

    assert value == datetime(2026, 10, 1, 0, 0, tzinfo=UTC)


@pytest.mark.unit
def test_un_istante_con_offset_viene_riportato_in_utc() -> None:
    value = as_utc(datetime(2026, 10, 1, 2, 0, tzinfo=timezone(timedelta(hours=2))))

    assert value.utcoffset() == timedelta(0)
    assert value == datetime(2026, 10, 1, 0, 0, tzinfo=UTC)


@pytest.mark.unit
def test_un_valore_non_rappresentabile_in_utc_e_un_errore_di_validazione() -> None:
    with pytest.raises(ValueError):
        as_utc(datetime(1, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=1))))


@pytest.mark.unit
def test_il_bulk_read_rifiuta_il_byte_nul_nella_ricerca() -> None:
    with pytest.raises(ValidationError):
        BulkReadIn(q="ab\x00cd")


@pytest.mark.unit
def test_il_bulk_read_normalizza_from_e_to_in_utc() -> None:
    body = BulkReadIn.model_validate({"from": "2026-10-01T00:00:00", "to": "2026-10-02T00:00:00"})

    assert body.from_ == datetime(2026, 10, 1, tzinfo=UTC)
    assert body.to == datetime(2026, 10, 2, tzinfo=UTC)
