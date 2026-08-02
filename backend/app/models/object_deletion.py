from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class PendingObjectDeletion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "pending_object_deletions"

    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
