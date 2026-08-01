import pytest

from app.models.notification import Notification
from app.models.severity_rule import SeverityRule


@pytest.mark.unit
def test_colonna_metadata_mappata_come_meta():
    assert Notification.meta.property.columns[0].name == "metadata"
    assert Notification.meta.key == "meta"


@pytest.mark.unit
def test_notification_id_generato_in_python():
    id_col = Notification.id.property.columns[0]
    assert id_col.default is not None
    assert id_col.server_default is None


@pytest.mark.unit
def test_pattern_lunghezza_massima():
    pattern_col = SeverityRule.__table__.c.pattern
    assert pattern_col.type.length == 200
