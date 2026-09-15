"""Unit del motore di audit (spec 9.6): nessuna dipendenza esterna, solo le
funzioni pure e il contratto del contesto di richiesta."""

import uuid
from datetime import UTC, datetime

import pytest

from app.db.types import AuditOutcome, Severity, UserRole
from app.models.channel import DeliveryChannel
from app.models.notification import Notification
from app.services.audit import (
    ACTION_MARKED_READ,
    ACTION_MARKED_UNREAD,
    ACTION_MARKED_UNVERIFIED,
    ACTION_MARKED_VERIFIED,
    REDACTED,
    RESOURCE_SPECS,
    AuditContext,
    _changes_for_insert,
    _jsonable,
    _label_for,
    _notification_actions,
    current_audit_context,
    record_event,
    reset_audit_context,
    set_audit_context,
)


class _FakeSession:
    """Raccoglie gli oggetti aggiunti: record_event non deve fare altro che
    `session.add`, perche' l'evento deve vivere nella transazione del
    chiamante."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


@pytest.mark.unit
def test_jsonable_converte_enum_uuid_e_datetime():
    event_id = uuid.uuid4()
    moment = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    assert _jsonable(Severity.WARNING) == "warning"
    assert _jsonable(event_id) == str(event_id)
    assert _jsonable(moment) == moment.isoformat()
    assert _jsonable(None) is None
    assert _jsonable(True) is True
    assert _jsonable(b"1234") == "<4 bytes>"


@pytest.mark.unit
def test_jsonable_tronca_i_valori_lunghi():
    value = _jsonable("x" * 900)
    assert value.endswith("…")
    assert len(value) == 501


@pytest.mark.unit
def test_changes_for_insert_maschera_i_segreti():
    channel = DeliveryChannel(
        tenant_id=uuid.uuid4(),
        name="Slack ops",
        type="slack",
        webhook_url=b"ciphertext",
        enabled=True,
    )
    changes = _changes_for_insert(channel, RESOURCE_SPECS[DeliveryChannel])

    # Il cambiamento si vede, il segreto no: chi legge l'audit non deve poterne
    # ricavare la credenziale del canale.
    assert changes["webhook_url"]["after"] == REDACTED
    assert changes["name"]["after"] == "Slack ops"
    assert "last_error" not in changes


@pytest.mark.unit
def test_notification_label_e_troncata_e_senza_a_capo():
    notification = Notification(
        tenant_id=uuid.uuid4(),
        receiver_id=uuid.uuid4(),
        content_preview="riga uno\nriga due " + "x" * 400,
        content_size=1,
        severity=Severity.INFO,
        severity_source="receiver_default",
        received_at=datetime.now(UTC),
    )
    label = _label_for(notification, RESOURCE_SPECS[Notification])

    assert label is not None
    assert "\n" not in label
    assert len(label) == 255


@pytest.mark.unit
def test_le_notifiche_espongono_solo_stato_e_verifica():
    spec = RESOURCE_SPECS[Notification]
    assert spec.fields == frozenset({"status", "verified"})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"status": {"before": "unread", "after": "read"}}, [ACTION_MARKED_READ]),
        ({"status": {"before": "read", "after": "unread"}}, [ACTION_MARKED_UNREAD]),
        ({"verified": {"before": False, "after": True}}, [ACTION_MARKED_VERIFIED]),
        ({"verified": {"before": True, "after": False}}, [ACTION_MARKED_UNVERIFIED]),
        (
            {
                "status": {"before": "unread", "after": "read"},
                "verified": {"before": False, "after": True},
            },
            [ACTION_MARKED_READ, ACTION_MARKED_VERIFIED],
        ),
    ],
)
def test_azioni_dedicate_per_lettura_e_verifica(changes, expected):
    """Una PATCH che cambia entrambi e' due fatti distinti, non uno."""
    assert _notification_actions(changes) == expected


@pytest.mark.unit
def test_record_event_aggiunge_senza_flush():
    session = _FakeSession()
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    audit_event = record_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        actor_email="owner@test.com",
        actor_role=UserRole.OWNER,
        action="notification.marked_read",
        resource_type="notification",
        resource_id=actor_id,
        outcome=AuditOutcome.SUCCESS,
    )

    assert session.added == [audit_event]
    assert audit_event.tenant_id == tenant_id
    assert audit_event.outcome == AuditOutcome.SUCCESS
    # changes/context vuoti restano NULL invece di {}: il filtro "ha un diff"
    # deve poter essere un IS NOT NULL.
    assert audit_event.changes is None
    assert audit_event.context is None


@pytest.mark.unit
def test_record_event_tronca_user_agent_e_label():
    session = _FakeSession()
    audit_event = record_event(
        session,
        tenant_id=uuid.uuid4(),
        actor_user_id=None,
        actor_email="a@b.c",
        actor_role=UserRole.ADMIN,
        action="receiver.updated",
        resource_type="receiver",
        resource_label="l" * 400,
        user_agent="u" * 400,
    )
    assert len(audit_event.resource_label) == 255
    assert len(audit_event.user_agent) == 255


@pytest.mark.unit
def test_contesto_assente_di_default_e_ripristinato():
    """Senza contesto non nasce alcun evento: e' cosi' che ingestion e job
    Celery restano fuori dall'audit pur usando le stesse sessioni."""
    assert current_audit_context() is None

    context = AuditContext(
        tenant_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        actor_role=UserRole.MEMBER,
    )
    token = set_audit_context(context)
    assert current_audit_context() is context
    reset_audit_context(token)
    assert current_audit_context() is None
