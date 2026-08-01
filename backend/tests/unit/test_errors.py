import pytest

from app.core.errors import INGEST_NOT_FOUND_BODY


@pytest.mark.unit
def test_corpo_404_ingest_e_costante():
    assert isinstance(INGEST_NOT_FOUND_BODY, dict)
    assert "slug" not in str(INGEST_NOT_FOUND_BODY)
    assert "disabled" not in str(INGEST_NOT_FOUND_BODY)
    assert "receiver" not in str(INGEST_NOT_FOUND_BODY)
    assert "tenant" not in str(INGEST_NOT_FOUND_BODY)
