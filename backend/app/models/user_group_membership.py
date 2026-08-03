import uuid

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserGroupMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_group_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_group_memberships_user_id_group_id"),
        Index("ix_user_group_memberships_tenant_id_group_id", "tenant_id", "group_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
