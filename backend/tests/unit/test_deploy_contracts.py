"""Contratti dei file di deploy (compose, nginx, Dockerfile, env): letti come testo o YAML, senza Docker."""

import asyncio
import ipaddress
from pathlib import Path

import pytest
import yaml
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

REPO = Path(__file__).resolve().parents[3]


def _compose() -> dict:
    return yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))


async def _client_visto_dall_app(trusted_hosts: str, peer: str, xff: str) -> str:
    visto: dict[str, tuple[str, int]] = {}

    async def app(scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        visto["client"] = scope["client"]

    middleware = ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts)
    scope = {
        "type": "http",
        "client": (peer, 4321),
        "headers": [(b"x-forwarded-for", xff.encode("latin1"))],
    }
    await middleware(scope, None, None)  # type: ignore[arg-type]
    return visto["client"][0]


@pytest.mark.unit
def test_api_si_fida_di_xff_solo_dal_nginx_del_compose():
    compose = _compose()
    ip_nginx = compose["services"]["nginx"]["networks"]["notifyhub"]["ipv4_address"]
    subnet = compose["networks"]["notifyhub"]["ipam"]["config"][0]["subnet"]
    fidati = compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"]

    # Un solo IP fidato (non un CIDR, non "*"): il resto della rete non puo' falsare il client.
    assert fidati == ip_nginx
    assert ipaddress.ip_address(ip_nginx) in ipaddress.ip_network(subnet)


@pytest.mark.unit
def test_xff_del_client_arriva_all_app_con_il_nginx_del_compose():
    compose = _compose()
    fidati = compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"]
    ip_nginx = compose["services"]["nginx"]["networks"]["notifyhub"]["ipv4_address"]

    # nginx aggiunge in coda l'IP vero del client; il client puo' solo mettere in testa altro.
    xff = "1.2.3.4, 198.51.100.4"

    visto = asyncio.run(_client_visto_dall_app(fidati, ip_nginx, xff))
    assert visto == "198.51.100.4"

    # Senza la fiducia configurata l'app vede solo il peer, cioe' nginx per tutti i client.
    senza_fiducia = asyncio.run(_client_visto_dall_app("127.0.0.1", ip_nginx, xff))
    assert senza_fiducia == ip_nginx
