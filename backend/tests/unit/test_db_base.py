import pytest

from app.db.base import Base


@pytest.mark.unit
def test_convenzione_nomi_presente():
    assert (
        Base.metadata.naming_convention["fk"]
        == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    )
