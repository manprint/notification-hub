import pytest
import re2


@pytest.mark.unit
def test_re2_importabile():
    pattern = re2.compile(r"FALL(ITO|IMENT)")
    match = pattern.search("Backup FALLITO")
    assert match is not None
    assert match.group(0) == "FALLITO"
