"""Contratti dei file di deploy (compose, nginx, Dockerfile, env), letti come testo o YAML."""

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


@pytest.mark.unit
@pytest.mark.parametrize("servizio", ["api", "worker"])
def test_api_e_worker_condividono_la_directory_delle_metriche(servizio):
    compose = _compose()
    svc = compose["services"][servizio]
    cartella = svc["environment"]["PROMETHEUS_MULTIPROC_DIR"]

    assert f"metricsdata:{cartella}" in svc["volumes"]
    assert "metricsdata" in compose["volumes"]
    # L'immagine crea la directory con l'utente dell'app, cosi' il volume nasce scrivibile.
    dockerfile = (REPO / "deploy/api/Dockerfile").read_text(encoding="utf-8")
    assert f"mkdir -p {cartella}" in dockerfile


@pytest.mark.unit
@pytest.mark.parametrize(
    "frammento",
    [
        "location = /index.html {",
        "expires -1;",
        "location /assets/ {",
        "try_files $uri =404;",
        "server_tokens off;",
        "gzip on;",
        "add_header X-Frame-Options DENY always;",
        "add_header X-Content-Type-Options nosniff always;",
    ],
)
def test_nginx_spa_ha_cache_e_intestazioni(frammento):
    # Il comportamento reale lo verifica deploy/nginx/test-headers.sh; qui il contratto testuale.
    nginx = (REPO / "deploy/nginx/nginx.conf").read_text(encoding="utf-8")
    assert frammento in nginx


def _valore_env(file_env: Path, nome: str) -> str:
    righe = file_env.read_text(encoding="utf-8").splitlines()
    valori = [r.split("=", 1)[1] for r in righe if r.startswith(f"{nome}=")]
    assert len(valori) == 1
    return valori[0]


@pytest.mark.unit
@pytest.mark.parametrize("file_env", [".env.example", ".env"])
def test_url_pubblica_di_default_e_quella_di_loopback_senza_porta_di_sviluppo(file_env):
    # Il worker non ha richieste da cui dedurre la URL: il default deve puntare alla porta
    # che nginx pubblica davvero (80), non a quella del dev server Vite (5173).
    from app.core.urls import DEFAULT_BASE_URL

    assert _valore_env(REPO / file_env, "NOTIFYHUB_PUBLIC_BASE_URL") == DEFAULT_BASE_URL


@pytest.mark.unit
@pytest.mark.parametrize("servizio", ["api", "worker", "beat"])
def test_solo_le_migrazioni_ricevono_il_ruolo_owner(servizio):
    # Il ruolo owner fa DDL e puo' disattivare l'RLS: a runtime non serve e non deve arrivare.
    env = _compose()["services"][servizio]["environment"]
    assert env["DATABASE_URL_OWNER"] == ""


@pytest.mark.unit
def test_migrate_ha_la_url_del_ruolo_owner():
    env = _compose()["services"]["migrate"]["environment"]
    assert env["DATABASE_URL_OWNER"].startswith("postgresql+asyncpg://notifyhub_owner:")


@pytest.mark.unit
def test_immagine_api_senza_compilatore_nello_stadio_finale():
    dockerfile = (REPO / "deploy/api/Dockerfile").read_text(encoding="utf-8")
    stadio_finale = dockerfile.split("\nFROM ")[-1]

    assert "gcc" not in stadio_finale
    assert "libpq-dev" not in stadio_finale
    assert "COPY --from=builder /opt/venv /opt/venv" in stadio_finale
