"""Invio verso i webhook Slack/Google Chat e calcolo del backoff (spec 8.2)."""

import random
from dataclasses import dataclass

import httpx

from app.core.logging import get_logger
from app.db.types import ChannelType
from app.outbound.formatters.google_chat import build_google_chat_payload
from app.outbound.formatters.slack import build_slack_payload

logger = get_logger(__name__)

# spec 8.2: 30s, 2m, 10m, 1h, 6h per i tentativi 1..5, con jitter.
_BACKOFF_SCHEDULE_SECONDS = [30, 120, 600, 3600, 21600]
MAX_ATTEMPTS = len(_BACKOFF_SCHEDULE_SECONDS)


def calculate_retry_delay(attempt_number: int) -> int:
    """Ritardo prima del prossimo tentativo, con jitter fino al 20% in piu.

    attempt_number e il numero del tentativo APPENA fallito (1-based). Oltre
    MAX_ATTEMPTS non ci sono altri retry: il chiamante deve gia aver marcato
    la delivery `dead` a quel punto, non richiamare questa funzione.
    """
    if attempt_number < 1 or attempt_number > MAX_ATTEMPTS:
        return 0
    base = _BACKOFF_SCHEDULE_SECONDS[attempt_number - 1]
    jitter = random.uniform(0, base * 0.2)  # noqa: S311 (jitter, non crittografico)
    return int(base + jitter)


@dataclass
class WebhookResult:
    ok: bool
    status_code: int | None
    retry_after: int | None
    error: str | None


def _build_payload(
    channel_type: ChannelType,
    *,
    receiver_name: str,
    severity: str,
    content_preview: str,
    content_size: int,
    notification_url: str,
) -> dict:
    if channel_type == ChannelType.SLACK:
        return build_slack_payload(
            receiver_name=receiver_name,
            severity=severity,
            content_preview=content_preview,
            content_size=content_size,
            notification_url=notification_url,
        )
    return build_google_chat_payload(
        receiver_name=receiver_name,
        severity=severity,
        content_preview=content_preview,
        content_size=content_size,
        notification_url=notification_url,
    )


def send_webhook_sync(
    channel_type: ChannelType,
    webhook_url: str,
    *,
    receiver_name: str,
    severity: str,
    content_preview: str,
    content_size: int,
    notification_url: str,
) -> WebhookResult:
    """Versione sincrona, usata dal worker Celery (spec 8.4: engine sincrono
    dedicato, niente event loop per task)."""
    payload = _build_payload(
        channel_type,
        receiver_name=receiver_name,
        severity=severity,
        content_preview=content_preview,
        content_size=content_size,
        notification_url=notification_url,
    )
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(webhook_url, json=payload)
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            return WebhookResult(
                ok=False, status_code=429, retry_after=retry_after, error="rate limited"
            )
        if response.is_success:
            return WebhookResult(
                ok=True, status_code=response.status_code, retry_after=None, error=None
            )
        return WebhookResult(
            ok=False,
            status_code=response.status_code,
            retry_after=None,
            error=f"HTTP {response.status_code}: {response.text[:200]}",
        )
    except httpx.HTTPError as exc:
        logger.error(
            "webhook_delivery_failed", webhook_host=webhook_url.split("/")[2], error=str(exc)
        )
        return WebhookResult(ok=False, status_code=None, retry_after=None, error=str(exc))
