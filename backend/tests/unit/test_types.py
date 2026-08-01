import pytest

from app.db.types import SEVERITY_ORDER, Severity


@pytest.mark.unit
def test_ordine_severity():
    assert list(Severity) == ["debug", "info", "warning", "error", "critical"]
    assert SEVERITY_ORDER["error"] > SEVERITY_ORDER["warning"]
    assert SEVERITY_ORDER["critical"] > SEVERITY_ORDER["error"]
