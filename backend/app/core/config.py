import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    notifyhub_secret_key: str
    database_url_owner: str
    database_url_app: str
    database_url_auth: str
    database_url_ingest: str
    database_url_sync: str
    redis_url: str
    celery_broker_url: str
    notifyhub_s3_endpoint: str
    notifyhub_s3_bucket: str
    notifyhub_s3_access_key: str
    notifyhub_s3_secret_key: str
    notifyhub_s3_region: str
    notifyhub_inline_max_bytes: int = 1048576
    notifyhub_hard_max_body_bytes: int = 20971520
    allow_public_registration: bool = False
    notifyhub_public_base_url: str
    # Percorso di scripts/notifyhub-run.sh, il template servito dal pulsante
    # "Scarica lo script". Vuoto = si cerca accanto al codice (vedi
    # app/services/wrapper_script.py): serve solo a deploy fuori standard.
    notifyhub_wrapper_script_path: str | None = None
    notifyhub_webhook_host_allowlist: str = "hooks.slack.com,chat.googleapis.com"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    cors_origins: str = ""
    trusted_proxies: str = ""
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"), extra="forbid", env_ignore_empty=True
    )

    @field_validator("notifyhub_secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("notifyhub_secret_key must be at least 32 characters long")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    @property
    def webhook_host_allowlist_list(self) -> list[str]:
        return [h.strip() for h in self.notifyhub_webhook_host_allowlist.split(",") if h.strip()]

    @property
    def smtp_enabled(self) -> bool:
        return self.smtp_host is not None and self.smtp_from is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
