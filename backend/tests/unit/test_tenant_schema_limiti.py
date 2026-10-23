"""Limiti di TenantUpdate allineati alle colonne (max_storage_bytes e BIGINT)."""

import pytest
from pydantic import ValidationError

from app.schemas.tenant import TenantUpdate


@pytest.mark.unit
def test_max_storage_bytes_oltre_bigint_non_passa_la_validazione():
    with pytest.raises(ValidationError):
        TenantUpdate(max_storage_bytes=2**63)


@pytest.mark.unit
def test_max_storage_bytes_al_limite_bigint_passa():
    assert TenantUpdate(max_storage_bytes=2**63 - 1).max_storage_bytes == 2**63 - 1
