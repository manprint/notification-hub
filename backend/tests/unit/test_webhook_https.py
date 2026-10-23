"""Unit: il webhook di un canale e' https, salvo gli host di dev dichiarati.

Il segreto del webhook sta nel percorso dell'URL: in http andrebbe in chiaro sulla
rete. Il passaggio http resta ammesso solo per gli host elencati in
NOTIFYHUB_WEBHOOK_INSECURE_HTTP_HOSTS (mock interno di dev e smoke test).
"""

from types import SimpleNamespace

import pytest

from app.api.v1 import channels
from app.core.errors import Problem


@pytest.fixture
def impostazioni(monkeypatch):
    def imposta(allowlist: list[str], http_hosts: list[str]) -> None:
        monkeypatch.setattr(
            channels,
            "get_settings",
            lambda: SimpleNamespace(
                webhook_host_allowlist_list=allowlist,
                webhook_insecure_http_hosts_list=http_hosts,
            ),
        )

    return imposta


def test_https_su_host_in_allowlist_e_accettato(impostazioni):
    impostazioni(["hooks.slack.com"], [])
    channels._validate_webhook_url("https://hooks.slack.com/services/T/B/X")


def test_http_su_host_in_allowlist_e_rifiutato(impostazioni):
    impostazioni(["hooks.slack.com"], [])
    with pytest.raises(Problem) as exc:
        channels._validate_webhook_url("http://hooks.slack.com/services/T/B/X")
    assert exc.value.status == 422
    assert "https" in exc.value.detail


def test_http_ammesso_solo_per_gli_host_di_dev_dichiarati(impostazioni):
    impostazioni(["hooks.slack.com", "mock-webhook"], ["mock-webhook"])
    channels._validate_webhook_url("http://mock-webhook:8899/hook")
    with pytest.raises(Problem):
        channels._validate_webhook_url("http://hooks.slack.com/services/T/B/X")


def test_https_su_host_fuori_allowlist_resta_rifiutato(impostazioni):
    impostazioni(["hooks.slack.com"], [])
    with pytest.raises(Problem) as exc:
        channels._validate_webhook_url("https://evil.example.com/hook")
    assert exc.value.status == 422
    assert "allowlist" in exc.value.detail


def test_schema_non_http_e_rifiutato(impostazioni):
    impostazioni(["hooks.slack.com"], [])
    with pytest.raises(Problem) as exc:
        channels._validate_webhook_url("ftp://hooks.slack.com/x")
    assert exc.value.status == 422
