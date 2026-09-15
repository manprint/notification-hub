import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.types import (
    AuditOutcome,
    UserRole,
    audit_outcome_type,
    user_role_type,
)


class AuditEvent(Base, UUIDPrimaryKeyMixin):
    """Registro di chi ha fatto cosa (spec 9.6).

    La riga e volutamente autosufficiente: `actor_email`, `actor_role` e
    `resource_label` sono fotografie del momento del fatto, non join da
    risolvere a posteriori. L'audit vive piu a lungo di cio che descrive
    (`tenants.audit_retention_days`, 365 giorni, contro i 90 di default delle
    notifiche), quindi una FK verso `notifications` cancellerebbe la storia con
    la purge o la renderebbe muta: `resource_id` e un uuid nudo.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_tenant_id_occurred_at_id", "tenant_id", "occurred_at", "id"),
        Index(
            "ix_audit_events_tenant_id_resource_type_resource_id_occurred_at",
            "tenant_id",
            "resource_type",
            "resource_id",
            "occurred_at",
        ),
        Index(
            "ix_audit_events_tenant_id_actor_user_id_occurred_at",
            "tenant_id",
            "actor_user_id",
            "occurred_at",
        ),
        Index("ix_audit_events_tenant_id_action_occurred_at", "tenant_id", "action", "occurred_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # ON DELETE SET NULL: cancellare un utente non deve cancellare la sua
    # storia. Chi era lo dicono comunque actor_email e actor_role, congelati
    # qui sotto.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str] = mapped_column(String(320), nullable=False)
    actor_role: Mapped[UserRole] = mapped_column(user_role_type, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    resource_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[AuditOutcome] = mapped_column(audit_outcome_type, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # {"campo": {"before": ..., "after": ...}}, con i segreti gia mascherati:
    # chi legge l'audit non deve poterci ricavare una credenziale di canale.
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Dati dell'operazione che non sono un diff di campi: i filtri e gli id di
    # un bulk-read, il motivo di un login fallito.
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
