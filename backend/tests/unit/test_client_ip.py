"""Risoluzione dell'IP di origine (spec 10.1, 10.2): `X-Forwarded-For` conta solo
dietro un proxy fidato, e la voce che conta e la piu a destra non fidata: quella
che il primo proxy fidato ha visto. Le voci a sinistra le scrive il client."""

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.api.deps import client_ip
from app.core.config import Settings, get_settings


def _request(client_host: str, headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/ingest/x",
            "raw_path": b"/ingest/x",
            "query_string": b"",
            "root_path": "",
            "server": ("testserver", 80),
            "client": (client_host, 54321),
            "headers": [
                (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
            ],
        }
    )


def _with_proxies(monkeypatch, trusted: str) -> None:
    settings = get_settings().model_copy(update={"trusted_proxies": trusted})
    monkeypatch.setattr("app.api.deps.get_settings", lambda: settings)


@pytest.mark.unit
def test_client_ip_non_si_fida_della_voce_di_sinistra_scritta_dal_client(monkeypatch):
    """`$proxy_add_x_forwarded_for` accoda il vero IP a quello che il client ha
    gia mandato: il primo valore e suo. Prenderlo significa cambiare chiave di
    rate limit a ogni richiesta."""
    _with_proxies(monkeypatch, "10.9.0.1")

    spoofed = _request("10.9.0.1", {"x-forwarded-for": "6.6.6.6, 203.0.113.7"})
    assert client_ip(spoofed) == "203.0.113.7"


@pytest.mark.unit
def test_client_ip_accetta_reti_cidr_fra_i_proxy_fidati(monkeypatch):
    """Il proxy del deploy ha un IP che cambia con la rete Docker: una rete CIDR
    deve bastare a riconoscerlo, altrimenti tutti i client collassano sull'IP
    del proxy."""
    _with_proxies(monkeypatch, "172.16.0.0/12")

    assert client_ip(_request("172.18.0.5", {"x-forwarded-for": "203.0.113.7"})) == "203.0.113.7"


@pytest.mark.unit
def test_client_ip_attraversa_una_catena_di_proxy_fidati(monkeypatch):
    _with_proxies(monkeypatch, "10.0.0.0/8")

    chain = _request("10.0.0.1", {"x-forwarded-for": "1.1.1.1, 10.0.0.5, 10.0.0.9"})
    assert client_ip(chain) == "1.1.1.1"


@pytest.mark.unit
def test_client_ip_con_tutte_le_voci_fidate_usa_la_piu_a_sinistra(monkeypatch):
    _with_proxies(monkeypatch, "10.0.0.0/8")

    assert client_ip(_request("10.0.0.1", {"x-forwarded-for": "10.0.0.5, 10.0.0.9"})) == "10.0.0.5"


@pytest.mark.unit
def test_client_ip_torna_al_peer_se_la_voce_non_fidata_non_e_un_ip(monkeypatch):
    """L'audit scrive questo valore in una colonna VARCHAR(45): un valore
    arbitrario che non parsa come IP non deve mai arrivarci."""
    _with_proxies(monkeypatch, "10.9.0.1")

    assert client_ip(_request("10.9.0.1", {"x-forwarded-for": "A" * 60})) == "10.9.0.1"
    assert client_ip(_request("10.9.0.1", {"x-forwarded-for": "1.1.1.1, garbage"})) == "10.9.0.1"


@pytest.mark.unit
def test_client_ip_non_accetta_ipv6_con_zona_di_scope(monkeypatch):
    """`fe80::1%<zona>` supera ipaddress ma allunga la stringa oltre le 45 colonne
    dell'audit: viene trattato come non valido."""
    _with_proxies(monkeypatch, "10.9.0.1")

    scoped = "fe80::1%" + "x" * 50
    assert client_ip(_request("10.9.0.1", {"x-forwarded-for": scoped})) == "10.9.0.1"


@pytest.mark.unit
def test_client_ip_peer_non_ip_non_e_mai_fidato(monkeypatch):
    _with_proxies(monkeypatch, "10.9.0.1")

    assert client_ip(_request("testclient", {"x-forwarded-for": "1.2.3.4"})) == "testclient"


@pytest.mark.unit
def test_client_ip_senza_proxy_dichiarati_ignora_x_forwarded_for(monkeypatch):
    _with_proxies(monkeypatch, "")

    assert client_ip(_request("198.51.100.4", {"x-forwarded-for": "1.2.3.4"})) == "198.51.100.4"


@pytest.mark.unit
def test_trusted_proxies_rifiuta_una_voce_non_valida():
    """Un TRUSTED_PROXIES scritto male deve fermare l'avvio: altrimenti la
    risoluzione dell'IP sparisce in silenzio e i limiti tornano a essere globali."""
    with pytest.raises(ValidationError, match="trusted_proxies"):
        Settings(trusted_proxies="10.0.0.0/33")
