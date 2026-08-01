import pytest

from app.core.logging import _redact_secrets


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
