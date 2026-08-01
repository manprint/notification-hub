import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import OverrideMode, Severity, override_mode_type, severity_type


class GroupChannelBinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "group_channel_bindings"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "channel_id", name="uq_group_channel_bindings_group_id_channel_id"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("delivery_channels.id"), nullable=False
    )
    min_severity: Mapped[Severity] = mapped_column(severity_type, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False)


class ReceiverChannelOverride(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "receiver_channel_overrides"
    __table_args__ = (
        UniqueConstraint(
            "receiver_id", "channel_id", name="uq_receiver_channel_overrides_receiver_id_channel_id"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    receiver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receivers.id"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("delivery_channels.id"), nullable=False
    )
    mode: Mapped[OverrideMode] = mapped_column(override_mode_type, nullable=False)
    min_severity: Mapped[Severity | None] = mapped_column(severity_type, nullable=True)
