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


class SeveritySource(StrEnum):
    EXPLICIT = "explicit"
    RULE = "rule"
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
