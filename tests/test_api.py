from fastapi.testclient import TestClient

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings


def app_settings(token: str | None = None) -> Settings:
    return Settings(
        gateway_token=token,
        providers=(ProviderSpec("local", "openai", "http://local", ("m",)),),
    )


def test_health_and_models() -> None:
    client = TestClient(create_app(app_settings()))
    assert client.get("/healthz").status_code == 200
    models = client.get("/v1/models")
    assert models.status_code == 200
    assert models.json()["data"][0]["id"] == "auto"


def test_gateway_auth() -> None:
    client = TestClient(create_app(app_settings("secret")))
    assert client.get("/v1/models").status_code == 401
    response = client.get("/v1/models", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200


def test_admin_provider_state_uses_gateway_auth() -> None:
    client = TestClient(create_app(app_settings("secret")))
    assert client.get("/admin/providers").status_code == 401

    response = client.get(
        "/admin/providers",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    assert response.json()["local"]["adapter"] == "openai"


def test_health_remains_public_when_gateway_auth_is_enabled() -> None:
    client = TestClient(create_app(app_settings("secret")))
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_request_id_is_preserved_when_supplied() -> None:
    client = TestClient(create_app(app_settings()))
    response = client.get("/healthz", headers={"x-request-id": "trace-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "trace-123"


def test_request_id_is_generated_when_absent() -> None:
    client = TestClient(create_app(app_settings()))
    response = client.get("/healthz")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    assert all(character in "0123456789abcdef" for character in request_id)
