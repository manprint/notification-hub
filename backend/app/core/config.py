import ipaddress
import os
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    notifyhub_secret_key: str
    # Usato solo da Alembic (che legge os.environ): api, worker e beat non lo ricevono.
    database_url_owner: str | None = None
    database_url_app: str
    database_url_auth: str
    database_url_ingest: str
    database_url_sync: str
    redis_url: str
    # Senza timeout di socket un Redis che smette di rispondere (ma tiene aperta
    # la connessione) blocca ogni ingestion per il tempo di keepalive del kernel.
    redis_socket_connect_timeout_seconds: float = 1.0
    redis_socket_timeout_seconds: float = 2.0
    celery_broker_url: str
    notifyhub_s3_endpoint: str
    notifyhub_s3_bucket: str
    notifyhub_s3_access_key: str
    notifyhub_s3_secret_key: str
    notifyhub_s3_region: str
    # Timeout espliciti sul client S3: senza, botocore aspetta 60 s per ogni
    # tentativo e il PUT tiene una connessione del pool per minuti (spec 6.5).
    notifyhub_s3_connect_timeout_seconds: float = 5.0
    notifyhub_s3_read_timeout_seconds: float = 30.0
    notifyhub_s3_max_attempts: int = 3
    notifyhub_inline_max_bytes: int = 1048576
    notifyhub_hard_max_body_bytes: int = 20971520
    allow_public_registration: bool = False
    notifyhub_public_base_url: str
    # Percorso di scripts/notifyhub-run.sh, il template servito dal pulsante
    # "Scarica lo script". Vuoto = si cerca accanto al codice (vedi
    # app/services/wrapper_script.py): serve solo a deploy fuori standard.
    notifyhub_wrapper_script_path: str | None = None
    notifyhub_webhook_host_allowlist: str = "hooks.slack.com,chat.googleapis.com"
    # Host per cui e' ammesso http:// nel webhook: solo dev e smoke test con un mock
    # interno. Il webhook porta il segreto nel percorso, quindi in produzione resta vuoto.
    notifyhub_webhook_insecure_http_hosts: str = ""
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
        # Il valore di esempio di .env.example e' pubblico: chi lo conosce firma JWT validi.
        # Basta il prefisso, che copre il valore di esempio e le sue varianti.
        if v.lower().startswith("change-me"):
            raise ValueError(
                "notifyhub_secret_key is the example placeholder: generate one with "
                "`openssl rand -hex 32`"
            )
        return v

    @field_validator("trusted_proxies")
    @classmethod
    def validate_trusted_proxies(cls, v: str) -> str:
        # Ogni voce e un IP singolo o una rete CIDR. Una voce scritta male deve
        # fermare l'avvio, non far cadere in silenzio la risoluzione dell'IP.
        for entry in (p.strip() for p in v.split(",") if p.strip()):
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(f"trusted_proxies: voce non valida {entry!r}") from exc
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    @property
    def trusted_proxy_networks(
        self,
    ) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        # Ricalcolata a ogni chiamata: la lista e corta e cosi i test che la
        # cambiano con model_copy (che salta i validator) restano coerenti.
        return [ipaddress.ip_network(p, strict=False) for p in self.trusted_proxies_list]

    @property
    def webhook_host_allowlist_list(self) -> list[str]:
        return [h.strip() for h in self.notifyhub_webhook_host_allowlist.split(",") if h.strip()]

    @property
    def webhook_insecure_http_hosts_list(self) -> list[str]:
        return [
            h.strip() for h in self.notifyhub_webhook_insecure_http_hosts.split(",") if h.strip()
        ]

    @property
    def smtp_enabled(self) -> bool:
        return self.smtp_host is not None and self.smtp_from is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def s3_timeouts(settings: Settings | None = None) -> dict[str, Any]:
    """Timeout e tentativi del client S3, dalle impostazioni NOTIFYHUB_S3_*: una sola
    fonte per il PUT in ingestion, il drain e la purge degli orfani (spec 6.5)."""
    if settings is None:
        settings = get_settings()
    return {
        "connect_timeout": settings.notifyhub_s3_connect_timeout_seconds,
        "read_timeout": settings.notifyhub_s3_read_timeout_seconds,
        "retries": {"max_attempts": settings.notifyhub_s3_max_attempts},
    }
