import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import ReceiverStatus, Severity, receiver_status_type, severity_type


class Receiver(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "receivers"
    __table_args__ = (Index("ix_receivers_tenant_id_group_id", "tenant_id", "group_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(22), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ReceiverStatus] = mapped_column(receiver_status_type, nullable=False)
    ingestion_module: Mapped[str] = mapped_column(String, nullable=False, default="http_raw")
    default_severity: Mapped[Severity] = mapped_column(
        severity_type, nullable=False, default="info"
    )
    max_body_bytes: Mapped[int] = mapped_column(nullable=False)
    rate_limit_per_min: Mapped[int] = mapped_column(nullable=False, default=60)
