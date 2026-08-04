from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ReceiverStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationPhase(StrEnum):
    """Fase dell'esecuzione dichiarata dal mittente nell'header `X-Phase`.

    Serve a distinguere due guasti che senza di essa sono indistinguibili: "il
    cron non e' mai partito" e "il job e' partito e non e' mai arrivato alla
    fine" (macchina caduta a meta' backup). NULL sulla notifica = il mittente non
    ha dichiarato niente, che e' il caso di tutto lo storico e di qualunque
    ingestion fatta a mano.
    """

    START = "start"
    END = "end"


class SeveritySource(StrEnum):
    EXPLICIT = "explicit"
    EXIT_CODE = "exit_code"
    # Durata dell'esecuzione oltre la soglia del receiver: un job riuscito ma
    # lento non lascia tracce nel proprio output, quindi il fatto arriva come
    # dato (header X-Duration-Ms) e non come testo da cercare con una regola.
    DURATION = "duration"
    # Notifica che NON e' arrivata: la genera il job di sorveglianza quando un
    # receiver sfora la propria attesa (macchina spenta, cron disabilitato, rete
    # verso NotifyHub assente). Nessuno script l'ha inviata.
    MISSING = "missing"
    # Rientro dopo un'assenza segnalata: chiude il cerchio sul canale dove e'
    # arrivato l'allarme. Severity fissa `info`.
    RECOVERED = "recovered"
    RULE = "rule"
    # Regola arrivata da un preset applicato al receiver, non scritta sul
    # receiver stesso: distinguerle serve a sapere dove andare a correggere.
    PRESET_RULE = "preset_rule"
    RECEIVER_DEFAULT = "receiver_default"


class NotificationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"


class StorageBackend(StrEnum):
    INLINE = "inline"
    OBJECT = "object"


class ChannelType(StrEnum):
    SLACK = "slack"
    GOOGLE_CHAT = "google_chat"


class OverrideMode(StrEnum):
    OVERRIDE = "override"
    MUTE = "mute"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.DEBUG: 10,
    Severity.INFO: 20,
    Severity.WARNING: 30,
    Severity.ERROR: 40,
    Severity.CRITICAL: 50,
}


def _values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


tenant_status_type = ENUM(
    TenantStatus, name="tenant_status", create_type=False, values_callable=_values
)
user_role_type = ENUM(UserRole, name="user_role", create_type=False, values_callable=_values)
user_status_type = ENUM(UserStatus, name="user_status", create_type=False, values_callable=_values)
receiver_status_type = ENUM(
    ReceiverStatus, name="receiver_status", create_type=False, values_callable=_values
)
severity_type = ENUM(Severity, name="severity", create_type=False, values_callable=_values)
severity_source_type = ENUM(
    SeveritySource, name="severity_source", create_type=False, values_callable=_values
)
notification_status_type = ENUM(
    NotificationStatus, name="notification_status", create_type=False, values_callable=_values
)
storage_backend_type = ENUM(
    StorageBackend, name="storage_backend", create_type=False, values_callable=_values
)
channel_type_type = ENUM(
    ChannelType, name="channel_type", create_type=False, values_callable=_values
)
override_mode_type = ENUM(
    OverrideMode, name="override_mode", create_type=False, values_callable=_values
)
delivery_status_type = ENUM(
    DeliveryStatus, name="delivery_status", create_type=False, values_callable=_values
)
notification_phase_type = ENUM(
    NotificationPhase, name="notification_phase", create_type=False, values_callable=_values
)
