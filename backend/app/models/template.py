import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class NotificationTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notification_templates"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title_template: Mapped[str] = mapped_column(String(500), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    default_severity: Mapped[str] = mapped_column(String(50), nullable=False, default="info")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    variables: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
