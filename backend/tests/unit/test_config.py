from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.mark.unit
def test_chiave_troppo_corta_rifiutata(monkeypatch):
    monkeypatch.setenv("NOTIFYHUB_SECRET_KEY", "short")
    monkeypatch.setenv("DATABASE_URL_OWNER", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_APP", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_AUTH", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_INGEST", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost/1")
    monkeypatch.setenv("NOTIFYHUB_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("NOTIFYHUB_S3_BUCKET", "bucket")
    monkeypatch.setenv("NOTIFYHUB_S3_ACCESS_KEY", "key")
    monkeypatch.setenv("NOTIFYHUB_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("NOTIFYHUB_S3_REGION", "us-east-1")
    monkeypatch.setenv("NOTIFYHUB_PUBLIC_BASE_URL", "http://localhost:3000")
    monkeypatch.delenv("ENV_FILE", raising=False)

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.unit
def test_registrazione_pubblica_disattiva_per_default(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NOTIFYHUB_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_URL_OWNER", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_APP", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_AUTH", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_INGEST", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost/1")
    monkeypatch.setenv("NOTIFYHUB_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("NOTIFYHUB_S3_BUCKET", "bucket")
    monkeypatch.setenv("NOTIFYHUB_S3_ACCESS_KEY", "key")
    monkeypatch.setenv("NOTIFYHUB_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("NOTIFYHUB_S3_REGION", "us-east-1")
    monkeypatch.setenv("NOTIFYHUB_PUBLIC_BASE_URL", "http://localhost:3000")
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("ALLOW_PUBLIC_REGISTRATION", raising=False)

    s = Settings()
    assert s.allow_public_registration is False
    get_settings.cache_clear()


@pytest.mark.unit
def test_smtp_disabilitato_se_incompleto(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NOTIFYHUB_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_URL_OWNER", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_APP", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_AUTH", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_INGEST", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost/1")
    monkeypatch.setenv("NOTIFYHUB_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("NOTIFYHUB_S3_BUCKET", "bucket")
    monkeypatch.setenv("NOTIFYHUB_S3_ACCESS_KEY", "key")
    monkeypatch.setenv("NOTIFYHUB_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("NOTIFYHUB_S3_REGION", "us-east-1")
    monkeypatch.setenv("NOTIFYHUB_PUBLIC_BASE_URL", "http://localhost:3000")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)

    s = Settings()
    assert s.smtp_enabled is False
    get_settings.cache_clear()


@pytest.mark.unit
def test_cors_origins_parsate(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NOTIFYHUB_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DATABASE_URL_OWNER", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_APP", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_AUTH", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_INGEST", "postgresql://localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql://localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost/1")
    monkeypatch.setenv("NOTIFYHUB_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("NOTIFYHUB_S3_BUCKET", "bucket")
    monkeypatch.setenv("NOTIFYHUB_S3_ACCESS_KEY", "key")
    monkeypatch.setenv("NOTIFYHUB_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("NOTIFYHUB_S3_REGION", "us-east-1")
    monkeypatch.setenv("NOTIFYHUB_PUBLIC_BASE_URL", "http://localhost:3000")
    monkeypatch.setenv("CORS_ORIGINS", "http://a,http://b")
    monkeypatch.delenv("ENV_FILE", raising=False)

    s = Settings()
    assert s.cors_origins_list == ["http://a", "http://b"]
    get_settings.cache_clear()


_REPO = Path(__file__).resolve().parents[3]


def _ambiente_minimo(monkeypatch: pytest.MonkeyPatch, chiave: str) -> None:
    monkeypatch.setenv("NOTIFYHUB_SECRET_KEY", chiave)
    for nome in (
        "DATABASE_URL_OWNER",
        "DATABASE_URL_APP",
        "DATABASE_URL_AUTH",
        "DATABASE_URL_INGEST",
        "DATABASE_URL_SYNC",
    ):
        monkeypatch.setenv(nome, "postgresql://localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost/1")
    monkeypatch.setenv("NOTIFYHUB_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("NOTIFYHUB_S3_BUCKET", "bucket")
    monkeypatch.setenv("NOTIFYHUB_S3_ACCESS_KEY", "key")
    monkeypatch.setenv("NOTIFYHUB_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("NOTIFYHUB_S3_REGION", "us-east-1")
    monkeypatch.setenv("NOTIFYHUB_PUBLIC_BASE_URL", "http://localhost:3000")
    monkeypatch.delenv("ENV_FILE", raising=False)


@pytest.mark.unit
@pytest.mark.parametrize(
    "chiave",
    [
        "change-me-32-bytes-minimum-000000",
        "Change-Me-un-valore-abbastanza-lungo-0123456789",
    ],
)
def test_chiave_di_esempio_rifiutata(monkeypatch, chiave):
    _ambiente_minimo(monkeypatch, chiave)

    with pytest.raises(ValidationError, match="placeholder"):
        Settings(_env_file=None)


@pytest.mark.unit
@pytest.mark.parametrize(
    "file_env",
    [".env", "backend/.env.test", "backend/.env.migration.test"],
)
def test_file_env_tracciati_non_usano_la_chiave_di_esempio(file_env):
    # Ogni file tracciato ha una chiave propria, di sviluppo, non quella di .env.example.
    righe = (_REPO / file_env).read_text(encoding="utf-8").splitlines()
    chiavi = [r.split("=", 1)[1] for r in righe if r.startswith("NOTIFYHUB_SECRET_KEY=")]

    assert len(chiavi) == 1
    assert len(chiavi[0]) >= 32
    assert not chiavi[0].lower().startswith("change-me")


@pytest.mark.unit
def test_runtime_si_avvia_senza_il_ruolo_owner(monkeypatch):
    _ambiente_minimo(monkeypatch, "a" * 32)
    monkeypatch.setenv("DATABASE_URL_OWNER", "")  # come nel compose per api, worker e beat

    s = Settings(_env_file=None)
    assert s.database_url_owner is None
