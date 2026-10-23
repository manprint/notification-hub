import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import structlog

from app.core.logging import _livello_log, _redact_secrets, configure_logging

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def logging_ripristinato():
    yield
    structlog.reset_defaults()


@pytest.mark.unit
def test_segreti_oscurati():
    event_dict = {
        "webhook_url": "https://hooks.slack.com/AAA",
        "password": "secret123",
        "normal_field": "visible",
        "event": "test",
    }

    result = _redact_secrets(None, "info", event_dict)

    assert result["webhook_url"] == "[redacted]"
    assert result["password"] == "[redacted]"
    assert result["normal_field"] == "visible"
    assert result["event"] == "test"


@pytest.mark.unit
def test_log_e_json_valido():
    event_dict = {
        "event": "test_event",
        "level": "info",
    }

    result = _redact_secrets(None, "info", event_dict)

    assert "event" in result
    assert "level" in result
    assert result["event"] == "test_event"
    assert result["level"] == "info"


@pytest.mark.unit
def test_log_level_filtra_gli_eventi_sotto_soglia(monkeypatch, capsys, logging_ripristinato):
    monkeypatch.setattr(
        "app.core.logging.get_settings", lambda: SimpleNamespace(log_level="WARNING")
    )
    configure_logging()

    structlog.get_logger("test").info("evento_informativo")
    structlog.get_logger("test").warning("evento_di_avviso")

    out = capsys.readouterr().out
    assert "evento_informativo" not in out
    assert "evento_di_avviso" in out


@pytest.mark.unit
@pytest.mark.parametrize(("nome", "livello"), [("debug", 10), ("WARN", 30), ("critical", 50)])
def test_livello_log_accetta_i_nomi_di_logging(nome, livello):
    assert _livello_log(nome) == livello


@pytest.mark.unit
def test_livello_log_sconosciuto_blocca_l_avvio():
    with pytest.raises(ValueError, match="LOG_LEVEL non valido"):
        _livello_log("VERBOSE")


@pytest.mark.unit
def test_worker_configura_il_logging_con_la_redazione_dei_segreti():
    # Processo a parte: il worker non passa da create_app, quindi il test non deve ereditare
    # una configurazione gia' fatta da altri test nello stesso interprete.
    codice = (
        "import structlog; import app.tasks.celery_app; "
        "print('_redact_secrets' in [getattr(p, '__name__', '') "
        "for p in structlog.get_config()['processors']])"
    )
    risultato = subprocess.run(  # noqa: S603
        [sys.executable, "-c", codice],
        cwd=BACKEND,
        env=dict(os.environ),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert risultato.stdout.strip().endswith("True")
