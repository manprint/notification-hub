import pytest
from sqlalchemy import UniqueConstraint

from app.models.tenant import Tenant
from app.models.user import User


@pytest.mark.unit
def test_email_utente_unica_globalmente():
    email_constraints = [
        c
        for c in User.__table__.constraints
        if isinstance(c, UniqueConstraint) and tuple(c.columns.keys()) == ("email",)
    ]
    assert len(email_constraints) == 1
    composite_email_constraints = [
        c
        for c in User.__table__.constraints
        if isinstance(c, UniqueConstraint) and tuple(c.columns.keys()) == ("tenant_id", "email")
    ]
    assert len(composite_email_constraints) == 0


@pytest.mark.unit
def test_tenant_ha_colonne_quota():
    assert "max_notifications_per_day" in Tenant.__table__.columns
    assert "max_storage_bytes" in Tenant.__table__.columns


@pytest.mark.unit
def test_relazioni_non_lazy():
    assert Tenant.users.property.lazy == "raise"
