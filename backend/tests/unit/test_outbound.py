import pytest

from app.outbound.formatters.google_chat import GOOGLE_CHAT_BODY_LIMIT, build_google_chat_payload
from app.outbound.formatters.slack import SLACK_BODY_LIMIT, build_slack_payload
from app.outbound.sender import MAX_ATTEMPTS, calculate_retry_delay


@pytest.mark.unit
def test_backoff_schedule_rispetta_la_spec():
    """spec 8.2: 30s, 2m, 10m, 1h, 6h (5 tentativi), con jitter in piu (mai in meno)."""
    expected_base = [30, 120, 600, 3600, 21600]
    for attempt, base in enumerate(expected_base, start=1):
        delay = calculate_retry_delay(attempt)
        assert base <= delay <= base * 1.2


@pytest.mark.unit
def test_backoff_oltre_max_attempts_e_zero():
    assert calculate_retry_delay(MAX_ATTEMPTS + 1) == 0
    assert calculate_retry_delay(0) == 0


@pytest.mark.unit
def test_slack_payload_tronca_oltre_il_limite():
    long_body = "x" * (SLACK_BODY_LIMIT + 500)
    payload = build_slack_payload(
        receiver_name="Backup notturno",
        severity="error",
        content_preview=long_body,
        content_size=len(long_body) + 10_000,
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    section_text = payload["blocks"][1]["text"]["text"]
    assert len(section_text) < len(long_body) + 100
    assert "troncato" in section_text
    assert "ERROR" in payload["blocks"][0]["text"]["text"]
    assert "Backup notturno" in payload["blocks"][0]["text"]["text"]


@pytest.mark.unit
def test_slack_payload_non_tronca_sotto_il_limite():
    body = "tutto ok"
    payload = build_slack_payload(
        receiver_name="R",
        severity="info",
        content_preview=body,
        content_size=len(body),
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    assert payload["blocks"][1]["text"]["text"] == body


@pytest.mark.unit
def test_google_chat_payload_tronca_oltre_il_limite():
    long_body = "x" * (GOOGLE_CHAT_BODY_LIMIT + 500)
    payload = build_google_chat_payload(
        receiver_name="R",
        severity="critical",
        content_preview=long_body,
        content_size=len(long_body) + 10_000,
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    widgets = payload["cardsV2"][0]["card"]["sections"][0]["widgets"]
    text = widgets[0]["textParagraph"]["text"]
    assert "troncato" in text
    assert widgets[1]["buttonList"]["buttons"][0]["onClick"]["openLink"]["url"].startswith(
        "https://notifyhub.example.com"
    )
