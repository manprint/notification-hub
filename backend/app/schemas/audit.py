from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.types import AuditOutcome, UserRole


class AuditEventOut(BaseModel):
    id: str
    occurred_at: datetime
    # `actor_user_id` e' NULL quando l'utente e' stato cancellato; email e ruolo
    # restano quelli congelati al momento del fatto e non spariscono mai.
    actor_user_id: str | None
    actor_email: str
    actor_role: UserRole
    action: str
    resource_type: str
    resource_id: str | None
    resource_label: str | None
    outcome: AuditOutcome
    ip: str | None
    user_agent: str | None
    request_id: str | None
    changes: dict[str, Any] | None
    context: dict[str, Any] | None


class AuditEventListOut(BaseModel):
    events: list[AuditEventOut]
    next_cursor: str | None
