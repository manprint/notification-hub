from datetime import UTC, datetime, timedelta

import pytest

from app.outbound.formatters.duration import duration_note, format_duration_ms
from app.outbound.formatters.google_chat import GOOGLE_CHAT_BODY_LIMIT, build_google_chat_payload
from app.outbound.formatters.slack import SLACK_BODY_LIMIT, build_slack_payload
from app.outbound.sender import (
    MAX_ATTEMPTS,
    MAX_RETRY_AFTER_SECONDS,
    calculate_retry_delay,
    parse_retry_after,
)


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
def test_retry_after_accetta_secondi_data_http_e_valori_malformati():
    now = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
    assert parse_retry_after("120", now=now) == 120
    assert parse_retry_after("Tue, 11 Aug 2026 10:02:00 GMT", now=now) == 120
    assert parse_retry_after("non-una-data", now=now) == 60
    assert parse_retry_after(None, now=now) == 60
    past = (now - timedelta(minutes=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after(past, now=now) == 1


@pytest.mark.unit
def test_retry_after_enorme_e_limitato_al_massimo_del_backoff():
    """Un Retry-After di 300000000000 secondi (o una data lontana nel futuro) farebbe
    sforare la data di prossimo tentativo in phase 3: il valore resta entro il tetto."""
    now = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
    assert parse_retry_after("300000000000", now=now) == MAX_RETRY_AFTER_SECONDS
    far = "Tue, 11 Aug 9999 10:00:00 GMT"
    assert parse_retry_after(far, now=now) == MAX_RETRY_AFTER_SECONDS


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


def _slack_section(payload: dict) -> str:
    return next(b for b in payload["blocks"] if b["type"] == "section")["text"]["text"]


def _slack_kwargs(**overrides: object) -> dict:
    kwargs: dict = {
        "receiver_name": "R",
        "severity": "error",
        "content_preview": "corpo",
        "content_size": len("corpo"),
        "notification_url": "https://notifyhub.example.com/notifications/abc",
    }
    kwargs.update(overrides)
    return kwargs


@pytest.mark.unit
def test_slack_header_non_supera_i_150_caratteri_e_conserva_la_severita():
    """L'header block di Slack e' limitato a 150 caratteri: un nome receiver lungo
    (fino a 255 nello schema) farebbe rifiutare l'intero messaggio."""
    payload = build_slack_payload(**_slack_kwargs(receiver_name="n" * 255))
    header = payload["blocks"][0]["text"]["text"]
    assert len(header) <= 150
    assert header.startswith("ERROR — ")
    assert header.endswith("…")


@pytest.mark.unit
def test_slack_corpo_vuoto_produce_una_section_con_testo():
    """Slack rifiuta una section con testo vuoto: un corpo vuoto ha un segnaposto."""
    payload = build_slack_payload(**_slack_kwargs(content_preview="", content_size=0))
    assert _slack_section(payload) != ""


@pytest.mark.unit
def test_slack_escapa_mrkdwn_per_non_pingare_il_canale_ne_creare_link():
    """`<!channel>`, `<url|label>` e `&` sono markup per Slack: vanno escapati."""
    payload = build_slack_payload(
        **_slack_kwargs(
            content_preview="<!channel> a & <https://x|y>",
            content_size=len("<!channel> a & <https://x|y>"),
        )
    )
    assert _slack_section(payload) == "&lt;!channel&gt; a &amp; &lt;https://x|y&gt;"


@pytest.mark.unit
def test_slack_il_limite_vale_sul_testo_escapato_e_non_taglia_entita():
    """4096 `&` escapati diventano 5 caratteri ciascuno: il tetto della section
    (3000) deve valere sull'output, e il taglio non cade dentro `&amp;`."""
    body = "&" * 4096
    payload = build_slack_payload(
        **_slack_kwargs(content_preview=body, content_size=len(body))
    )
    text = _slack_section(payload)
    assert len(text) <= 3000
    main, notice = text.split("\n… [troncato", 1)
    assert main == "&amp;" * (SLACK_BODY_LIMIT // 5)
    assert notice.startswith(", 4 KB totali]")


@pytest.mark.unit
def test_slack_nessun_falso_troncato_quando_la_normalizzazione_rimuove_nul():
    """Il corpo `hello\\x00 world` (12 byte) e' intero: la preview 'hello world' e'
    piu' corta dei byte originali, ma non e' un troncamento."""
    payload = build_slack_payload(
        **_slack_kwargs(content_preview="hello world", content_size=12)
    )
    assert _slack_section(payload) == "hello world"


@pytest.mark.unit
def test_google_chat_nessun_falso_troncato_quando_la_normalizzazione_rimuove_nul():
    payload = build_google_chat_payload(
        receiver_name="R",
        severity="error",
        content_preview="hello world",
        content_size=12,
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    text = payload["cardsV2"][0]["card"]["sections"][0]["widgets"][0]["textParagraph"]["text"]
    assert text == "hello world"


@pytest.mark.unit
def test_google_chat_preview_salvata_troncata_dichiara_il_troncamento():
    """Una preview al tetto di salvataggio (4096) con byte originali in più è un
    troncamento reale: la segnalazione resta."""
    body = "x" * 4096
    payload = build_google_chat_payload(
        receiver_name="R",
        severity="error",
        content_preview=body,
        content_size=5000,
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    text = payload["cardsV2"][0]["card"]["sections"][0]["widgets"][0]["textParagraph"]["text"]
    assert "troncato, 4 KB totali" in text


@pytest.mark.unit
def test_google_chat_escapa_il_markup_del_corpo():
    """Google Chat renderizza il testo come HTML semplice: `<a href>` ingerito non
    deve diventare un link con testo scelto dal mittente."""
    body = '<a href="https://evil">x</a> & <b>'
    payload = build_google_chat_payload(
        receiver_name="R",
        severity="error",
        content_preview=body,
        content_size=len(body),
        notification_url="https://notifyhub.example.com/notifications/abc",
    )
    text = payload["cardsV2"][0]["card"]["sections"][0]["widgets"][0]["textParagraph"]["text"]
    assert text == '&lt;a href="https://evil"&gt;x&lt;/a&gt; &amp; &lt;b&gt;'


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


@pytest.mark.unit
def test_safe_error_toglie_url_path_e_query_del_webhook():
    from app.outbound.sender import safe_error

    url = "https://chat.googleapis.com/v1/spaces/AAA/messages?key=SEGRETO&token=ALTRO"
    testo = safe_error(ValueError(f"errore su {url} (path /v1/spaces/AAA/messages)"), url)
    assert "SEGRETO" not in testo
    assert "/v1/spaces/AAA/messages" not in testo
    assert "chat.googleapis.com" in testo
    assert testo.startswith("ValueError: ")


@pytest.mark.unit
def test_safe_error_senza_messaggio_restituisce_il_tipo():
    from app.outbound.sender import safe_error

    assert safe_error(TimeoutError(), "https://hooks.slack.com/services/T/B/X") == "TimeoutError"
