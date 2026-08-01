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
