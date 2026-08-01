import httpx
import pytest

from app.main import create_app


@pytest.mark.e2e
async def test_healthz_ritorna_ok():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.e2e
async def test_rotta_inesistente_ritorna_404():
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/non-esiste")
        assert response.status_code == 404
