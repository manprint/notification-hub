import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.types import DeliveryStatus, delivery_status_type


class Delivery(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "channel_id", name="uq_deliveries_notification_id_channel_id"
        ),
        Index(
            "ix_deliveries_status_next_attempt_at",
            "status",
            "next_attempt_at",
            postgresql_where="status IN ('pending', 'failed')",
        ),
        Index(
            "ix_deliveries_status_locked_at",
            "status",
            "locked_at",
            postgresql_where="status='sending'",
        ),
        Index("ix_deliveries_tenant_id_channel_id_status", "tenant_id", "channel_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("delivery_channels.id"), nullable=False
    )
    status: Mapped[DeliveryStatus] = mapped_column(delivery_status_type, nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_code: Mapped[int | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
