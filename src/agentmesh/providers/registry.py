from __future__ import annotations

from agentmesh.config import ProviderSpec
from agentmesh.providers.anthropic import AnthropicProvider
from agentmesh.providers.base import Provider
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider


class ProviderRegistry:
    def __init__(self, specs: tuple[ProviderSpec, ...]) -> None:
        self.specs = {spec.name: spec for spec in specs}
        self.providers: dict[str, Provider] = {}
        for spec in specs:
            if spec.adapter == "openai":
                provider: Provider = OpenAICompatibleProvider(spec)
            else:
                provider = AnthropicProvider(spec)
            self.providers[spec.name] = provider

    def get(self, name: str) -> Provider:
        return self.providers[name]
