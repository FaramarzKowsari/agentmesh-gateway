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
