from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import TenantStatus, tenant_status_type

if TYPE_CHECKING:
    from app.models.user import User


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    max_body_bytes: Mapped[int] = mapped_column(nullable=False, default=1048576)
    max_notifications_per_day: Mapped[int | None] = mapped_column(nullable=True)
    max_storage_bytes: Mapped[int | None] = mapped_column(nullable=True)
    retention_days: Mapped[int | None] = mapped_column(nullable=True, default=90)
    status: Mapped[TenantStatus] = mapped_column(tenant_status_type, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="tenant", lazy="raise")
