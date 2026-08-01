import pytest


@pytest.mark.e2e
async def test_request_id_propagato(api_client):
    response = await api_client.get("/healthz", headers={"x-request-id": "abc-123"})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "abc-123"


@pytest.mark.e2e
async def test_request_id_generato_se_assente(api_client):
    response = await api_client.get("/healthz")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert len(request_id) > 0
