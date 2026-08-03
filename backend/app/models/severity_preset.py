import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import Severity, severity_type


class SeverityPreset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Insieme di regole riusabile, applicabile a piu receiver.

    I preset predefiniti (bash-generic, postgres, ...) vengono COPIATI dentro il
    tenant al momento dell'installazione: da li in poi sono righe come tutte le
    altre e si modificano dalla dashboard. `builtin_key` non da immunita, dice
    solo da quale voce del catalogo la copia e nata, e serve a due cose: non
    reinstallare due volte lo stesso preset e sapere a quali valori tornare con
    il ripristino.
    """

    __tablename__ = "severity_presets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_severity_presets_tenant_id_name"),
        # NULL non collide con NULL in Postgres: i preset creati a mano restano
        # senza chiave di catalogo e non si ostacolano fra loro.
        UniqueConstraint(
            "tenant_id", "builtin_key", name="uq_severity_presets_tenant_id_builtin_key"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    builtin_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")


class SeverityPresetRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Regola dentro un preset. Stessa forma di SeverityRule, senza receiver_id:
    il legame con i receiver passa da ReceiverSeverityPreset."""

    __tablename__ = "severity_preset_rules"
    __table_args__ = (
        UniqueConstraint(
            "preset_id", "priority", name="uq_severity_preset_rules_preset_id_priority"
        ),
        Index(
            "ix_severity_preset_rules_tenant_id_preset_id_priority",
            "tenant_id",
            "preset_id",
            "priority",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    preset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("severity_presets.id", ondelete="CASCADE"), nullable=False
    )
    priority: Mapped[int] = mapped_column(nullable=False)
    pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    case_insensitive: Mapped[bool] = mapped_column(nullable=False, default=True)
    severity: Mapped[Severity] = mapped_column(severity_type, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)


class ReceiverSeverityPreset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Preset applicato a un receiver. `position` fissa l'ordine fra piu preset:
    conta quando due preset diversi corrispondono allo stesso messaggio."""

    __tablename__ = "receiver_severity_presets"
    __table_args__ = (
        UniqueConstraint(
            "receiver_id", "preset_id", name="uq_receiver_severity_presets_receiver_id_preset_id"
        ),
        UniqueConstraint(
            "receiver_id", "position", name="uq_receiver_severity_presets_receiver_id_position"
        ),
        Index(
            "ix_receiver_severity_presets_tenant_id_receiver_id_position",
            "tenant_id",
            "receiver_id",
            "position",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receivers.id", ondelete="CASCADE"), nullable=False
    )
    preset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("severity_presets.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(nullable=False)
