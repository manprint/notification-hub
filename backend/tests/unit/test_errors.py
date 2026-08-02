import pytest

from app.core.errors import ingest_not_found


@pytest.mark.unit
def test_corpo_404_ingest_e_costante():
    """Il 404 uniforme (spec 9.1, I-2) non deve rivelare quale dei tre casi
    (slug inesistente, disabled, suspended) l'ha generato."""
    p1 = ingest_not_found()
    p2 = ingest_not_found()
    assert (p1.status, p1.type, p1.title, p1.detail) == (p2.status, p2.type, p2.title, p2.detail)
    assert "slug" not in p1.detail.lower()
    assert "disabled" not in p1.detail.lower()
    assert "tenant" not in p1.detail.lower()
