import uuid

import pytest

from app.services.delivery import (
    ChannelType,
    DeliveryPayload,
    build_google_chat_payload,
    build_slack_payload,
)


@pytest.mark.unit
def test_channel_type_enum():
    assert ChannelType.SLACK.value == "slack"
    assert ChannelType.GOOGLE_CHAT.value == "google_chat"
    assert ChannelType.EMAIL.value == "email"
    assert ChannelType.WEBHOOK.value == "webhook"


@pytest.mark.unit
def test_delivery_payload_dataclass():
    notification_id = uuid.uuid4()

    payload = DeliveryPayload(
        notification_id=notification_id,
        title="Test Alert",
        body="This is a test notification",
        severity="error",
        webhook_url="https://hooks.slack.com/services/T1234/B1234/X1234",
        channel_type=ChannelType.SLACK,
    )

    assert payload.notification_id == notification_id
    assert payload.title == "Test Alert"
    assert payload.body == "This is a test notification"
    assert payload.severity == "error"
    assert payload.channel_type == ChannelType.SLACK


@pytest.mark.unit
def test_slack_color_map():
    """Verify Slack payload structure for critical severity."""
    import asyncio

    notification_id = uuid.uuid4()
    payload = DeliveryPayload(
        notification_id=notification_id,
        title="Critical Alert",
        body="System down",
        severity="critical",
        webhook_url="https://hooks.slack.com/services/T1234/B1234/X1234",
        channel_type=ChannelType.SLACK,
    )

    result = asyncio.run(build_slack_payload(payload))
    assert "blocks" in result
    assert result["attachments"][0]["color"] == "#990000"


@pytest.mark.unit
def test_google_chat_payload_structure():
    """Verify Google Chat payload structure."""
    import asyncio

    notification_id = uuid.uuid4()
    payload = DeliveryPayload(
        notification_id=notification_id,
        title="Warning Alert",
        body="High memory usage",
        severity="warning",
        webhook_url="https://chat.googleapis.com/v1/spaces/ABC/messages",
        channel_type=ChannelType.GOOGLE_CHAT,
    )

    result = asyncio.run(build_google_chat_payload(payload))
    assert "cards" in result
    assert "Severity: WARNING" in result["cards"][0]["header"]["subtitle"]
