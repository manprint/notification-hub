import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import ReceiverStatus, Severity, receiver_status_type, severity_type
from app.services.slug import SLUG_MAX_CHARS  # solo stdlib: nessun ciclo di import


class Receiver(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "receivers"
    __table_args__ = (
        Index("ix_receivers_tenant_id_group_id", "tenant_id", "group_id"),
        # Soglia e severity della durata vivono insieme: una soglia senza
        # severity non saprebbe cosa assegnare, una severity senza soglia non
        # scatterebbe mai. Il vincolo tiene fuori dal database lo stato mezzo
        # configurato, che l'API rifiuterebbe comunque con 422.
        CheckConstraint(
            "(duration_threshold_seconds IS NULL AND duration_severity IS NULL) "
            "OR (duration_threshold_seconds IS NOT NULL AND duration_severity IS NOT NULL "
            "AND duration_threshold_seconds > 0)",
            name="ck_receivers_duration_policy",
        ),
        # Sorveglianza dell'attesa (migrazione 0012): spenta del tutto, oppure
        # completa con esattamente uno fra intervallo ed espressione cron.
        CheckConstraint(
            """
        (
            expected_every_seconds IS NULL AND expected_cron IS NULL
            AND expected_grace_seconds IS NULL AND missing_severity IS NULL
            AND expected_timezone IS NULL
        )
        OR (
            (
                (expected_every_seconds IS NOT NULL AND expected_cron IS NULL
                 AND expected_every_seconds > 0)
                OR (expected_every_seconds IS NULL AND expected_cron IS NOT NULL)
            )
            AND expected_grace_seconds IS NOT NULL AND expected_grace_seconds >= 0
            AND missing_severity IS NOT NULL
            AND (expected_timezone IS NULL OR expected_cron IS NOT NULL)
        )
        """,
            name="ck_receivers_expected_policy",
        ),
        Index(
            "ix_receivers_expected_active",
            "tenant_id",
            postgresql_where=text("missing_severity IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    # `gruppo-receiver-token`, dove il token e' la parte casuale di 22 caratteri
    # (vedi services/slug.py). Larghezza dalla migrazione 0011.
    slug: Mapped[str] = mapped_column(
        String(SLUG_MAX_CHARS), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ReceiverStatus] = mapped_column(receiver_status_type, nullable=False)
    ingestion_module: Mapped[str] = mapped_column(String, nullable=False, default="http_raw")
    default_severity: Mapped[Severity] = mapped_column(
        severity_type, nullable=False, default="info"
    )
    # Severity assegnata quando l'ingestion riceve X-Exit-Code diverso da zero.
    # NULL = l'exit code non ha nessun effetto sulla severity.
    exit_code_severity: Mapped[Severity | None] = mapped_column(severity_type, nullable=True)
    # Durata oltre la quale la notifica prende `duration_severity`. NULL su
    # entrambe = la durata non ha nessun effetto (vedi il CHECK sopra).
    duration_threshold_seconds: Mapped[int | None] = mapped_column(nullable=True)
    duration_severity: Mapped[Severity | None] = mapped_column(severity_type, nullable=True)
    max_body_bytes: Mapped[int] = mapped_column(nullable=False)
    rate_limit_per_min: Mapped[int] = mapped_column(nullable=False, default=60)

    # --- sorveglianza dell'attesa (dead man's switch, migrazione 0012) --------
    # Ogni quanto ci si aspetta un invio. Uno solo dei due: intervallo fisso
    # oppure la stessa espressione che sta nel crontab, col suo fuso.
    expected_every_seconds: Mapped[int | None] = mapped_column(nullable=True)
    expected_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Tolleranza sul ritardo e severity dell'assenza.
    expected_grace_seconds: Mapped[int | None] = mapped_column(nullable=True)
    missing_severity: Mapped[Severity | None] = mapped_column(severity_type, nullable=True)
    # Da quando la politica e' in vigore: per un receiver che non ha mai
    # ricevuto niente e' questo l'istante da cui si conta l'attesa.
    expected_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Ultimo invio VERO (le notifiche sintetiche non la toccano, altrimenti la
    # sorveglianza si riarmerebbe da sola). Denormalizzata dall'ingestion per
    # non fare un max() su notifications ogni minuto.
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Ultimo ping di avvio visto (header X-Phase: start). Separato da
    # last_notification_at, che resta l'ultima CONCLUSIONE: se un avvio contasse
    # come conclusione, la sorveglianza tacerebbe proprio quando il job muore a
    # meta esecuzione. Con i due istanti la notifica di assenza sa dire se il job
    # non e' mai partito o se e' partito e non ha mai finito.
    last_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Assenza gia' segnalata: una notifica per assenza, riarmata al primo invio
    # vero. NULL = sorveglianza armata.
    missing_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
