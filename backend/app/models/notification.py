import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.types import (
    NotificationStatus,
    Severity,
    SeveritySource,
    StorageBackend,
    notification_status_type,
    severity_source_type,
    severity_type,
    storage_backend_type,
)


class Notification(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_tenant_id_received_at_id", "tenant_id", "received_at", "id"),
        Index(
            "ix_notifications_tenant_id_receiver_id_received_at_id",
            "tenant_id",
            "receiver_id",
            "received_at",
            "id",
        ),
        Index(
            "ix_notifications_tenant_id_status",
            "tenant_id",
            "status",
            postgresql_where="status='unread'",
        ),
        Index(
            "ix_notifications_content_preview_tsvector",
            "content_preview",
            postgresql_using="gin",
            postgresql_ops={"content_preview": "gin_trgm_ops"},
        ),
        Index(
            "ix_notifications_storage_key",
            "storage_key",
            postgresql_where="storage_backend='object'",
        ),
        CheckConstraint(
            (
                "(storage_backend = 'inline' AND content IS NOT NULL AND storage_key IS NULL) "
                "OR (storage_backend = 'object' AND content IS NULL AND storage_key IS NOT NULL)"
            ),
            name="ck_notifications_body",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receivers.id", ondelete="CASCADE"), nullable=False
    )
    storage_backend: Mapped[StorageBackend] = mapped_column(
        storage_backend_type, nullable=False, default="inline"
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    content_preview: Mapped[str] = mapped_column(String(4096), nullable=False)
    content_size: Mapped[int] = mapped_column(nullable=False)
    content_normalized: Mapped[bool] = mapped_column(nullable=False, default=False)
    severity: Mapped[Severity] = mapped_column(severity_type, nullable=False)
    severity_source: Mapped[SeveritySource] = mapped_column(severity_source_type, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        notification_status_type, nullable=False, default="unread"
    )
    received_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    source_ip: Mapped[str | None] = mapped_column(nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
