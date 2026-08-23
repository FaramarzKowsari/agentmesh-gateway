import pytest

from agentmesh.config import ProviderSpec, Settings
from agentmesh.errors import ConfigurationError


def test_provider_spec_rejects_unknown_adapter() -> None:
    with pytest.raises(ConfigurationError):
        ProviderSpec.from_dict(
            {"name": "x", "adapter": "weird", "base_url": "http://x", "models": ["m"]}
        )


def test_provider_spec_parses_explicit_capabilities() -> None:
    spec = ProviderSpec.from_dict(
        {
            "name": "x",
            "adapter": "responses",
            "base_url": "http://x",
            "models": ["m"],
            "capabilities": ["text", "tools", "reasoning", "tools"],
        }
    )

    assert spec.capabilities == ("text", "tools", "reasoning")
    assert spec.effective_capabilities() == frozenset({"text", "tools", "reasoning"})


def test_provider_spec_rejects_unknown_capability() -> None:
    with pytest.raises(ConfigurationError, match="unsupported capability"):
        ProviderSpec.from_dict(
            {
                "name": "x",
                "adapter": "openai",
                "base_url": "http://x",
                "models": ["m"],
                "capabilities": ["text", "telepathy"],
            }
        )


def test_provider_spec_default_capabilities_preserve_adapter_behavior() -> None:
    openai = ProviderSpec("openai", "openai", "http://x", ("m",))
    anthropic = ProviderSpec("anthropic", "anthropic", "http://x", ("m",))
    responses = ProviderSpec("responses", "responses", "http://x", ("m",))

    assert openai.effective_capabilities() == frozenset({"text", "tools"})
    assert anthropic.effective_capabilities() == frozenset({"text", "tools"})
    assert responses.effective_capabilities() == frozenset(
        {"text", "tools", "reasoning", "native_responses_tools"}
    )


def test_settings_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTMESH_PROVIDERS_JSON", raising=False)
    settings = Settings.from_env()
    assert settings.providers[0].name == "local-ollama"
