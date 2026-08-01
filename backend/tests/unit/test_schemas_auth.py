import pytest
from pydantic import ValidationError

from app.schemas.auth import InvitationAcceptIn, UserOut


@pytest.mark.unit
def test_password_corta_rifiutata():
    with pytest.raises(ValidationError):
        InvitationAcceptIn(token="t", password="corta")


@pytest.mark.unit
def test_user_out_non_espone_hash():
    assert "password_hash" not in UserOut.model_fields
