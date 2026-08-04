"""Formatter Google Chat cardV2 (spec 8.5). Idem slack.py: solo content_preview
e content_size, mai MinIO (invariante I-4)."""

from app.outbound.formatters.duration import duration_note

GOOGLE_CHAT_BODY_LIMIT = 3800


def build_google_chat_payload(
    *,
    receiver_name: str,
    severity: str,
    content_preview: str,
    content_size: int,
    notification_url: str,
    duration_ms: int | None = None,
    duration_threshold_seconds: int | None = None,
) -> dict:
    truncated = len(content_preview) > GOOGLE_CHAT_BODY_LIMIT or content_size > len(
        content_preview.encode()
    )
    body = content_preview[:GOOGLE_CHAT_BODY_LIMIT]
    if truncated:
        body += f"\n… [troncato, {content_size // 1024} KB totali]"

    # Il sottotitolo della card e' il posto dove Google Chat mette il contesto:
    # senza durata dichiarata la chiave resta fuori dal payload.
    note = duration_note(duration_ms, duration_threshold_seconds)
    header: dict = {"title": f"{severity.upper()} — {receiver_name}"}
    if note is not None:
        header["subtitle"] = f"⏱ {note}"

    return {
        "cardsV2": [
            {
                "cardId": "notifyhub-alert",
                "card": {
                    "header": header,
                    "sections": [
                        {
                            "widgets": [
                                {"textParagraph": {"text": body}},
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "Apri in NotifyHub",
                                                "onClick": {"openLink": {"url": notification_url}},
                                            }
                                        ]
                                    }
                                },
                            ]
                        }
                    ],
                },
            }
        ]
    }
