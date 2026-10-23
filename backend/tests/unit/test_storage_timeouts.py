"""Il client S3 ha timeout espliciti: un MinIO bloccato non deve tenere una
richiesta di ingestion per il default di botocore (60 s per tentativo)."""

import pytest

from app.services.storage import _client_kwargs


@pytest.mark.unit
def test_client_s3_ha_timeout_di_connessione_lettura_e_tentativi_espliciti(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings().model_copy(
        update={
            "notifyhub_s3_connect_timeout_seconds": 3.0,
            "notifyhub_s3_read_timeout_seconds": 12.0,
            "notifyhub_s3_max_attempts": 2,
        }
    )
    monkeypatch.setattr("app.services.storage.get_settings", lambda: settings)

    config = _client_kwargs()["config"]

    assert config.connect_timeout == 3.0
    assert config.read_timeout == 12.0
    assert config.retries == {"max_attempts": 2}
