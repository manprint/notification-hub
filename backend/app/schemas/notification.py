import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.db.types import NotificationPhase, NotificationStatus, Severity, SeveritySource

LIST_PREVIEW_CHARS = 500  # spec 9.5: la lista non restituisce il content completo


class NotificationListItemOut(BaseModel):
    id: str
    receiver_id: str
    content_preview: str
    content_size: int
    content_normalized: bool
    storage_backend: str
    severity: Severity
    severity_source: str
    # Fase dichiarata dal mittente: 'start' e' un ping di avvio, 'end' la
    # notifica che chiude l'esecuzione, NULL non dichiarata. In lista serve a non
    # confondere un avvio con un esito.
    phase: NotificationPhase | None = None
    # Dati dell'esecuzione dichiarati dal mittente (NULL se non li manda): stanno
    # anche in lista perche "quali job sono stati lenti" e una domanda da elenco,
    # non da dettaglio.
    duration_ms: int | None = None
    exit_code: int | None = None
    status: NotificationStatus
    verified: bool
    received_at: datetime


class NotificationListOut(BaseModel):
    notifications: list[NotificationListItemOut]
    next_cursor: str | None
    unread_count: int


class NotificationDetailOut(BaseModel):
    id: str
    receiver_id: str
    content: str | None
    content_url: str | None
    content_preview: str
    content_size: int
    content_normalized: bool
    severity: Severity
    severity_source: str
    phase: NotificationPhase | None = None
    matched_pattern: str | None
    duration_ms: int | None = None
    exit_code: int | None = None
    status: NotificationStatus
    verified: bool
    received_at: datetime
    source_ip: str | None


class MarkStatusIn(BaseModel):
    """Toggle di stato: almeno uno tra status e verified. Retro-compatibile:
    chi manda solo status (vecchi client) funziona identico."""

    status: NotificationStatus | None = None
    verified: bool | None = None

    @model_validator(mode="after")
    def _requires_at_least_one(self) -> "MarkStatusIn":
        if self.status is None and self.verified is None:
            raise ValueError("at least one of 'status' or 'verified' is required")
        return self


class BulkReadIn(BaseModel):
    """Segna in blocco per filtro (spec 9.5), non per lista di id: gli stessi
    filtri di GET /notifications, applicati a tutte le righe corrispondenti."""

    group_id: uuid.UUID | None = None
    receiver_id: uuid.UUID | None = None
    severity_min: Severity | None = None
    # Stesso filtro della lista: senza, "segna come letto tutto quello che
    # vedo" agirebbe anche su cio' che il filtro sull'origine sta escludendo.
    source: SeveritySource | None = None
    q: str | None = None
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None

    model_config = {"populate_by_name": True}


class BulkReadOut(BaseModel):
    marked_read: int


class StatsSummaryOut(BaseModel):
    total_unread: int
    by_severity: dict[str, int]
    by_group: list[dict]
    notifications_last_24h: int
    deliveries_dead: int
