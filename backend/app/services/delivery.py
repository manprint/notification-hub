import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class ChannelType(StrEnum):
    SLACK = "slack"
    GOOGLE_CHAT = "google_chat"
    EMAIL = "email"
    WEBHOOK = "webhook"


@dataclass
class DeliveryPayload:
    notification_id: uuid.UUID
    title: str
    body: str
    severity: str
    webhook_url: str
    channel_type: ChannelType


async def build_slack_payload(payload: DeliveryPayload) -> dict:
    """Build Slack webhook payload."""
    color_map = {
        "debug": "#808080",
        "info": "#0099FF",
        "warning": "#FF9900",
        "error": "#FF0000",
        "critical": "#990000",
    }

    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": payload.title},
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity*\n{payload.severity.upper()}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*ID*\n{payload.notification_id}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": payload.body},
            },
        ],
        "attachments": [
            {
                "color": color_map.get(payload.severity, "#999999"),
                "footer": "NotifyHub",
                "ts": int(datetime.now(UTC).timestamp()),
            }
        ],
    }


async def build_google_chat_payload(payload: DeliveryPayload) -> dict:
    """Build Google Chat webhook payload."""
    return {
        "text": f"{payload.title}",
        "cards": [
            {
                "header": {
                    "title": payload.title,
                    "subtitle": f"Severity: {payload.severity.upper()}",
                },
                "sections": [
                    {
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": payload.body,
                                }
                            },
                            {
                                "keyValue": {
                                    "topLabel": "Notification ID",
                                    "content": str(payload.notification_id),
                                }
                            },
                        ]
                    }
                ],
            }
        ],
    }


async def send_to_webhook(payload: DeliveryPayload) -> bool:
    """Send notification to webhook URL."""
    if payload.channel_type == ChannelType.SLACK:
        webhook_payload = await build_slack_payload(payload)
    elif payload.channel_type == ChannelType.GOOGLE_CHAT:
        webhook_payload = await build_google_chat_payload(payload)
    else:
        webhook_payload = {
            "notification_id": str(payload.notification_id),
            "title": payload.title,
            "body": payload.body,
            "severity": payload.severity,
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                payload.webhook_url,
                json=webhook_payload,
                headers={"User-Agent": "NotifyHub/1.0"},
            )
            response.raise_for_status()

        logger.info(
            "webhook_delivery_success",
            notification_id=payload.notification_id,
            webhook_url=payload.webhook_url,
            status=response.status_code,
        )
        return True
    except httpx.HTTPError as e:
        logger.error(
            "webhook_delivery_failed",
            notification_id=payload.notification_id,
            webhook_url=payload.webhook_url,
            error=str(e),
        )
        return False


async def schedule_retry(delivery_id: uuid.UUID, attempt_number: int) -> datetime:
    """Calculate next retry time using exponential backoff."""
    from app.services.storage import calculate_retry_delay

    delay_seconds = calculate_retry_delay(attempt_number)
    if delay_seconds == 0:
        return datetime.now(UTC) + timedelta(days=365)

    return datetime.now(UTC) + timedelta(seconds=delay_seconds)
