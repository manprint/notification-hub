"""Formatter Slack Block Kit (spec 8.5). Formatta solo da content_preview e
content_size: il worker non legge mai content ne oggetti MinIO (invariante I-4)."""

from app.outbound.formatters.duration import duration_note

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
    duration_ms: int | None = None,
    duration_threshold_seconds: int | None = None,
) -> dict:
    truncated = len(content_preview) > SLACK_BODY_LIMIT or content_size > len(
        content_preview.encode()
    )
    body = content_preview[:SLACK_BODY_LIMIT]
    if truncated:
        body += f"\n… [troncato, {content_size // 1024} KB totali]"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{severity.upper()} — {receiver_name}"},
        },
    ]

    # Sopra il corpo, non dentro: la durata e il suo confronto con la soglia sono
    # il motivo dell'alert, il log e' la prova.
    note = duration_note(duration_ms, duration_threshold_seconds)
    if note is not None:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"⏱ {note}"}]})

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"<{notification_url}|Apri in NotifyHub>"}],
        }
    )

    return {
        "blocks": blocks,
        "attachments": [{"color": _COLOR_MAP.get(severity, "#999999")}],
    }
