"""Regressioni trovate nella revisione pre-staging (docs/REVIEW.md, "Verifica 3").

Ogni test qui dimostra un difetto reale del codice precedente: rimettendo la
vecchia implementazione, il test fallisce.
"""

import httpx
import pytest
from starlette.requests import Request

from app.api.deps import client_ip
from app.core.config import get_settings
from app.db.types import ChannelType
from app.outbound.sender import _host_of, send_webhook_sync


def _request(client_host: str, headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "root_path": "",
            "server": ("testserver", 80),
            "client": (client_host, 54321),
            "headers": [
                (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
            ],
        }
    )


def _settings_with_proxies(trusted: str):
    return get_settings().model_copy(update={"trusted_proxies": trusted})


@pytest.mark.unit
def test_client_ip_usa_x_forwarded_for_solo_da_un_proxy_dichiarato(monkeypatch):
    """Dietro nginx `request.client.host` e l'IP del proxy per ogni client: senza
    risolvere X-Forwarded-For il rate limit del login si riduce alla sola email e
    dieci tentativi sbagliati bastano a bloccare un account noto per tutti."""
    monkeypatch.setattr("app.api.deps.get_settings", lambda: _settings_with_proxies("10.9.0.1"))

    dal_proxy = _request("10.9.0.1", {"x-forwarded-for": "203.0.113.7, 10.9.0.1"})
    assert client_ip(dal_proxy) == "203.0.113.7"


@pytest.mark.unit
def test_client_ip_ignora_x_forwarded_for_da_un_mittente_non_fidato(monkeypatch):
    """L'header lo scrive il client: fidarsene sempre renderebbe ogni limite per
    IP aggirabile cambiando una stringa."""
    monkeypatch.setattr("app.api.deps.get_settings", lambda: _settings_with_proxies("10.9.0.1"))

    diretto = _request("198.51.100.4", {"x-forwarded-for": "1.2.3.4"})
    assert client_ip(diretto) == "198.51.100.4"


@pytest.mark.unit
def test_client_ip_senza_proxy_dichiarati_resta_sull_indirizzo_della_connessione(monkeypatch):
    monkeypatch.setattr("app.api.deps.get_settings", lambda: _settings_with_proxies(""))

    assert client_ip(_request("198.51.100.4", {"x-forwarded-for": "1.2.3.4"})) == "198.51.100.4"


@pytest.mark.unit
def test_send_webhook_sync_non_lascia_uscire_eccezioni_non_http(monkeypatch):
    """Un'eccezione che sfugge da send_webhook_sync esce da dispatch_delivery
    mentre la delivery e' `sending`: reconcile la riporta a `failed` dopo 10
    minuti, la riaccoda, si rompe di nuovo, per sempre, senza mai arrivare a
    `dead`. httpx.InvalidURL e gli errori di serializzazione del payload non
    sono httpx.HTTPError, che era l'unica classe intercettata."""

    def _boom(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise ValueError("payload non serializzabile")

    monkeypatch.setattr(httpx.Client, "post", _boom)

    result = send_webhook_sync(
        ChannelType.SLACK,
        "https://hooks.slack.com/services/T000/B000/XXXX",
        receiver_name="r",
        severity="error",
        content_preview="boom",
        content_size=4,
        notification_url="https://notifyhub.example.com/notifications/x",
    )

    assert result.ok is False
    assert result.status_code is None
    assert "payload non serializzabile" in (result.error or "")


@pytest.mark.unit
def test_host_of_non_solleva_su_url_malformato_e_non_rivela_il_path():
    """Il path di un webhook Slack/Google Chat E' il segreto: nel log ci va solo
    l'host. Lo split su "/" usato prima dava IndexError su una stringa senza
    doppio slash, cioe' proprio dentro il gestore d'errore."""
    assert _host_of("https://hooks.slack.com/services/T000/B000/SEGRETO") == "hooks.slack.com"
    assert _host_of("non-un-url") == "unknown"
    assert "SEGRETO" not in _host_of("https://hooks.slack.com/services/T000/B000/SEGRETO")
