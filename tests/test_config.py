import pytest

from agentmesh.config import ProviderSpec, Settings
from agentmesh.errors import ConfigurationError


def test_provider_spec_rejects_unknown_adapter() -> None:
    with pytest.raises(ConfigurationError):
        ProviderSpec.from_dict(
            {"name": "x", "adapter": "weird", "base_url": "http://x", "models": ["m"]}
        )


def test_settings_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTMESH_PROVIDERS_JSON", raising=False)
    settings = Settings.from_env()
    assert settings.providers[0].name == "local-ollama"
