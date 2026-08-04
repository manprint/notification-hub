"""`GET /readyz`: la sonda su cui si appoggiano gli healthcheck.

Era l'unico modulo dell'applicazione con **zero** copertura, e non e' un dettaglio:
`docker-compose.yml` e l'HEALTHCHECK dell'immagine all-in-one decidono da qui se il
container e' sano. Un `/readyz` che risponde sempre 200 nasconde un guasto (nessuno
riavvia niente); uno che risponde sempre 503 fa restare il container `unhealthy` e
puo' impedire un deploy.
"""

import pytest

from app.core import readiness


@pytest.mark.e2e
async def test_readyz_verde_con_tutte_le_dipendenze_su(api_client, migrated_db):
    """Contro i servizi reali di docker-compose.test.yml: Postgres, Redis e MinIO
    ci sono davvero, quindi l'esito deve essere 200 con tutti i controlli true."""
    resp = await api_client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    # I nomi dei controlli sono un contratto: chi diagnostica un container legge
    # questi, e rinominarli rompe le procedure in docs/OPERAZIONI.md.
    assert body["checks"] == {"postgres": True, "redis": True, "minio": True}


@pytest.mark.e2e
@pytest.mark.parametrize("dipendenza", ["postgres", "redis", "minio"])
async def test_readyz_rosso_se_una_dipendenza_manca(api_client, monkeypatch, dipendenza):
    """Una sola dipendenza giu' deve bastare per il 503: il container non e' in
    grado di servire, e dirlo a meta' sarebbe peggio che tacere."""

    async def _finto() -> dict[str, bool]:
        esiti = {"postgres": True, "redis": True, "minio": True}
        esiti[dipendenza] = False
        return esiti

    monkeypatch.setattr(readiness, "check_readiness", _finto)
    monkeypatch.setattr("app.core.readiness.check_readiness", _finto)

    resp = await api_client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"][dipendenza] is False


@pytest.mark.e2e
async def test_check_postgres_rosso_se_il_database_non_risponde(monkeypatch):
    """I tre controlli catturano l'eccezione e tornano False: se una lasciasse
    passare l'errore, `/readyz` risponderebbe 500 invece di 503 e l'healthcheck
    non saprebbe interpretarlo."""

    class _EngineRotto:
        def connect(self):
            raise OSError("connessione rifiutata")

    monkeypatch.setattr(readiness, "engine_app", _EngineRotto())
    assert await readiness._check_postgres() is False


@pytest.mark.e2e
async def test_check_redis_rosso_se_ping_alza(monkeypatch):
    async def _redis_rotto():
        raise ConnectionError("redis giu'")

    monkeypatch.setattr(readiness, "get_redis", _redis_rotto)
    assert await readiness._check_redis() is False


@pytest.mark.e2e
async def test_check_minio_rosso_su_bucket_inesistente(monkeypatch):
    """Bucket sbagliato = deposito dei payload non utilizzabile: e' un guasto, non
    una configurazione da ignorare."""
    from app.core.config import get_settings

    reali = get_settings()

    class _Settings:
        notifyhub_s3_endpoint = reali.notifyhub_s3_endpoint
        notifyhub_s3_access_key = reali.notifyhub_s3_access_key
        notifyhub_s3_secret_key = reali.notifyhub_s3_secret_key
        notifyhub_s3_region = reali.notifyhub_s3_region
        notifyhub_s3_bucket = "bucket-che-non-esiste-mai"

    monkeypatch.setattr(readiness, "get_settings", lambda: _Settings())
    assert await readiness._check_minio() is False


@pytest.mark.e2e
async def test_check_readiness_interroga_tutti_e_tre(api_client, migrated_db):
    esiti = await readiness.check_readiness()
    assert set(esiti) == {"postgres", "redis", "minio"}
    assert all(esiti.values()), f"dipendenze non raggiungibili: {esiti}"
