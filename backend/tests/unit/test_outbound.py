import pytest

from app.outbound.formatters.duration import duration_note, format_duration_ms
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


# --- durata nei messaggi ----------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ms", "atteso"),
    [
        (0, "0.000s"),
        (750, "0.750s"),
        (59_999, "59.999s"),
        (60_000, "1m00s"),
        (750_123, "12m30s"),
        (3_600_000, "1h00m00s"),
        (45_296_789, "12h34m56s"),
    ],
)
def test_format_duration_ms(ms, atteso):
    """Stessa resa del wrapper e del frontend: lo stesso job scritto uguale
    dappertutto."""
    assert format_duration_ms(ms) == atteso


@pytest.mark.unit
def test_duration_note_dichiara_la_soglia_solo_se_superata():
    assert duration_note(750_123, 600) == "durata 12m30s — oltre la soglia di 10m00s"
    assert duration_note(300_000, 600) == "durata 5m00s"
    assert duration_note(300_000, None) == "durata 5m00s"
    # Nessuna durata dichiarata: nessuna riga da mostrare.
    assert duration_note(None, 600) is None


@pytest.mark.unit
def test_slack_mostra_la_durata_sopra_il_corpo():
    payload = build_slack_payload(
        receiver_name="Backup notturno",
        severity="error",
        content_preview="tutto ok",
        content_size=8,
        notification_url="https://notifyhub.example.com/notifications/abc",
        duration_ms=750_123,
        duration_threshold_seconds=600,
    )
    contesto = payload["blocks"][1]["elements"][0]["text"]
    assert "12m30s" in contesto
    assert "oltre la soglia di 10m00s" in contesto
    # Il corpo resta un blocco a se, dopo la riga di contesto.
    assert payload["blocks"][2]["text"]["text"] == "tutto ok"


@pytest.mark.unit
def test_slack_senza_durata_non_aggiunge_blocchi():
    """Le notifiche che non arrivano dal wrapper non hanno durata: il messaggio
    deve restare identico a prima."""
    payload = build_slack_payload(
        receiver_name="R",
        severity="info",
        content_preview="corpo",
        content_size=5,
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    assert payload["blocks"][1]["text"]["text"] == "corpo"


@pytest.mark.unit
def test_google_chat_mette_la_durata_nel_sottotitolo():
    payload = build_google_chat_payload(
        receiver_name="R",
        severity="error",
        content_preview="corpo",
        content_size=5,
        notification_url="https://notifyhub.example.com/notifications/abc",
        duration_ms=750_123,
        duration_threshold_seconds=600,
    )
    header = payload["cardsV2"][0]["card"]["header"]
    assert "oltre la soglia" in header["subtitle"]

    senza = build_google_chat_payload(
        receiver_name="R",
        severity="error",
        content_preview="corpo",
        content_size=5,
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    assert "subtitle" not in senza["cardsV2"][0]["card"]["header"]
