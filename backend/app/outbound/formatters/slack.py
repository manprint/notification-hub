"""Formatter Slack Block Kit (spec 8.5). Formatta solo da content_preview e
content_size: il worker non legge mai content ne oggetti MinIO (invariante I-4)."""

SLACK_BODY_LIMIT = 2800

_COLOR_MAP = {
    "critical": "#990000",
    "error": "#FF0000",
    "warning": "#FF9900",
    "info": "#808080",
    "debug": "#808080",
}


def build_slack_payload(
    *,
    receiver_name: str,
    severity: str,
    content_preview: str,
    content_size: int,
    notification_url: str,
) -> dict:
    truncated = len(content_preview) > SLACK_BODY_LIMIT or content_size > len(
        content_preview.encode()
    )
    body = content_preview[:SLACK_BODY_LIMIT]
    if truncated:
        body += f"\n… [troncato, {content_size // 1024} KB totali]"

    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{severity.upper()} — {receiver_name}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": body},
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"<{notification_url}|Apri in NotifyHub>"}],
            },
        ],
        "attachments": [{"color": _COLOR_MAP.get(severity, "#999999")}],
    }
