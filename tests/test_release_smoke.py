from importlib.metadata import version as package_version

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agentmesh import __version__
from agentmesh.api.app import create_app
from agentmesh.cli import app as cli_app
from agentmesh.config import ProviderSpec, Settings


def release_settings() -> Settings:
    return Settings(
        providers=(
            ProviderSpec(
                name="local-smoke",
                adapter="openai",
                base_url="http://127.0.0.1:9/v1",
                models=("smoke-model",),
            ),
        )
    )


def test_package_and_runtime_versions_match_release() -> None:
    assert __version__ == "0.2.0"
    assert package_version("agentmesh-gateway") == __version__


def test_cli_version_matches_release() -> None:
    result = CliRunner().invoke(cli_app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "0.2.0"


def test_health_reports_release_version_without_provider_network() -> None:
    client = TestClient(create_app(release_settings()))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.2.0"}


def test_local_asgi_models_route_requires_no_provider_network() -> None:
    client = TestClient(create_app(release_settings()))

    response = client.get("/v1/models")

    assert response.status_code == 200
    assert response.json() == {
        "object": "list",
        "data": [
            {"id": "auto", "object": "model", "owned_by": "agentmesh"},
            {"id": "smoke-model", "object": "model", "owned_by": "local-smoke"},
        ],
    }
