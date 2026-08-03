import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import Severity, severity_type


class SeverityRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "severity_rules"
    __table_args__ = (
        # Due regole con la stessa priorita rendono indefinito quale vince:
        # l'unicita rende l'ordine di valutazione leggibile dalla tabella.
        UniqueConstraint("receiver_id", "priority", name="uq_severity_rules_receiver_id_priority"),
        Index(
            "ix_severity_rules_tenant_id_receiver_id_priority",
            "tenant_id",
            "receiver_id",
            "priority",
            postgresql_where="enabled",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receivers.id", ondelete="CASCADE"), nullable=False
    )
    priority: Mapped[int] = mapped_column(nullable=False)
    pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    case_insensitive: Mapped[bool] = mapped_column(nullable=False, default=True)
    severity: Mapped[Severity] = mapped_column(severity_type, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
