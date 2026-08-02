import uuid

import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    LoginIn,
    LogoutIn,
    MeOut,
    RefreshIn,
    TokenPairOut,
    UserOut,
    UserPatchIn,
)


@pytest.mark.unit
def test_login_in_schema():
    payload = LoginIn(email="user@example.com", password="password123")
    assert payload.email == "user@example.com"
    assert payload.password == "password123"


@pytest.mark.unit
def test_login_in_invalid_email():
    with pytest.raises(ValidationError):
        LoginIn(email="invalid-email", password="password123")


@pytest.mark.unit
def test_token_pair_out_schema():
    payload = TokenPairOut(
        access_token="access_123",
        refresh_token="refresh_123",
        token_type="bearer",
        expires_in=900,
    )
    assert payload.access_token == "access_123"
    assert payload.refresh_token == "refresh_123"
    assert payload.token_type == "bearer"
    assert payload.expires_in == 900


@pytest.mark.unit
def test_token_pair_out_default_type():
    payload = TokenPairOut(access_token="access_123", refresh_token="refresh_123", expires_in=900)
    assert payload.token_type == "bearer"


@pytest.mark.unit
def test_refresh_in_schema():
    payload = RefreshIn(refresh_token="refresh_token_123")
    assert payload.refresh_token == "refresh_token_123"


@pytest.mark.unit
def test_logout_in_default():
    payload = LogoutIn()
    assert payload.revoke_all is False
    assert payload.jti is None


@pytest.mark.unit
def test_logout_in_revoke_all():
    payload = LogoutIn(revoke_all=True)
    assert payload.revoke_all is True


@pytest.mark.unit
def test_logout_in_single_token():
    payload = LogoutIn(jti="token_jti_123")
    assert payload.revoke_all is False
    assert payload.jti == "token_jti_123"


@pytest.mark.unit
def test_me_out_schema():
    payload = MeOut(
        id="user-123",
        email="user@example.com",
        role="owner",
        tenant_id="tenant-123",
        tenant_name="Test Tenant",
    )
    assert payload.id == "user-123"
    assert payload.email == "user@example.com"
    assert payload.role == "owner"
    assert payload.tenant_id == "tenant-123"
    assert payload.tenant_name == "Test Tenant"


@pytest.mark.unit
def test_user_out_schema():
    user_id = str(uuid.uuid4())
    payload = UserOut(
        id=user_id,
        email="user@example.com",
        role="member",
        status="active",
        last_login_at=None,
    )
    assert str(payload.id) == user_id
    assert payload.email == "user@example.com"
    assert payload.role == "member"
    assert payload.status == "active"
    assert payload.last_login_at is None


@pytest.mark.unit
def test_user_patch_in_empty():
    payload = UserPatchIn()
    assert payload.role is None
    assert payload.status is None


@pytest.mark.unit
def test_user_patch_in_role():
    payload = UserPatchIn(role="admin")
    assert payload.role == "admin"
    assert payload.status is None


@pytest.mark.unit
def test_user_patch_in_status():
    payload = UserPatchIn(status="disabled")
    assert payload.role is None
    assert payload.status == "disabled"


@pytest.mark.unit
def test_user_patch_in_both():
    payload = UserPatchIn(role="viewer", status="active")
    assert payload.role == "viewer"
    assert payload.status == "active"
