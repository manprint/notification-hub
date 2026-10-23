"""Formatter Slack Block Kit (spec 8.5). Formatta solo da content_preview e
content_size: il worker non legge mai content ne oggetti MinIO (invariante I-4)."""

from app.outbound.formatters.duration import duration_note
from app.outbound.formatters.text import fit_escaped, is_stored_truncation

SLACK_BODY_LIMIT = 2800
# Il testo dell'header block di Slack e' limitato a 150 caratteri.
SLACK_HEADER_LIMIT = 150

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
    body, cut = fit_escaped(content_preview, SLACK_BODY_LIMIT)
    if cut or is_stored_truncation(content_preview, content_size):
        body += f"\n… [troncato, {content_size // 1024} KB totali]"
    # Una section con testo vuoto e' rifiutata da Slack: il corpo vuoto resta visibile.
    body = body or "(corpo vuoto)"

    header = f"{severity.upper()} — {receiver_name}"
    if len(header) > SLACK_HEADER_LIMIT:
        header = header[: SLACK_HEADER_LIMIT - 1] + "…"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header},
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
