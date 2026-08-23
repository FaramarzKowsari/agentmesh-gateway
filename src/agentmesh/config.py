from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal, cast

from agentmesh.errors import ConfigurationError

AdapterName = Literal["openai", "anthropic", "responses"]
RoutingPolicy = Literal["balanced", "latency", "cost", "quality", "ordered"]
Capability = Literal["text", "tools", "reasoning", "native_responses_tools"]

KNOWN_CAPABILITIES = frozenset(
    {
        "text",
        "tools",
        "reasoning",
        "native_responses_tools",
    }
)


def _parse_capabilities(value: object) -> tuple[Capability, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("capabilities must be a list")

    capabilities: list[Capability] = []
    for raw in value:
        capability = str(raw)
        if capability not in KNOWN_CAPABILITIES:
            raise ValueError(f"unsupported capability: {capability}")
        typed = cast(Capability, capability)
        if typed not in capabilities:
            capabilities.append(typed)
    return tuple(capabilities)


@dataclass(slots=True, frozen=True)
class ProviderSpec:
    name: str
    adapter: AdapterName
    base_url: str
    models: tuple[str, ...]
    api_key_env: str | None = None
    cost_hint: float = 0.5
    quality_hint: float = 0.5
    weight: float = 1.0
    timeout_seconds: float = 120.0
    capabilities: tuple[Capability, ...] | None = None

    def effective_capabilities(self) -> frozenset[Capability]:
        if self.capabilities is not None:
            return frozenset(self.capabilities)
        if self.adapter == "responses":
            return frozenset({"text", "tools", "reasoning", "native_responses_tools"})
        return frozenset({"text", "tools"})

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ProviderSpec:
        try:
            models = tuple(str(x) for x in data.get("models", []))
            if not models:
                raise ValueError("models must not be empty")
            adapter = str(data.get("adapter", "openai"))
            if adapter not in {"openai", "anthropic", "responses"}:
                raise ValueError(f"unsupported adapter: {adapter}")
            return cls(
                name=str(data["name"]),
                adapter=adapter,  # type: ignore[arg-type]
                base_url=str(data["base_url"]).rstrip("/"),
                models=models,
                api_key_env=str(data["api_key_env"]) if data.get("api_key_env") else None,
                cost_hint=float(data.get("cost_hint", 0.5)),
                quality_hint=float(data.get("quality_hint", 0.5)),
                weight=float(data.get("weight", 1.0)),
                timeout_seconds=float(data.get("timeout_seconds", 120.0)),
                capabilities=_parse_capabilities(data.get("capabilities")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"invalid provider specification: {exc}") from exc


@dataclass(slots=True, frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8787
    routing_policy: RoutingPolicy = "balanced"
    max_attempts: int = 3
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    gateway_token: str | None = None
    providers: tuple[ProviderSpec, ...] = ()

    @classmethod
    def from_env(cls) -> Settings:
        raw = os.getenv("AGENTMESH_PROVIDERS_JSON")
        if raw:
            try:
                decoded = json.loads(raw)
                if not isinstance(decoded, list):
                    raise ValueError("top-level value must be a list")
                providers = tuple(ProviderSpec.from_dict(item) for item in decoded)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ConfigurationError(f"invalid AGENTMESH_PROVIDERS_JSON: {exc}") from exc
        else:
            providers = (
                ProviderSpec(
                    name="local-ollama",
                    adapter="openai",
                    base_url="http://127.0.0.1:11434/v1",
                    models=("qwen2.5-coder:7b",),
                    cost_hint=0.0,
                    quality_hint=0.6,
                ),
            )

        policy = os.getenv("AGENTMESH_ROUTING_POLICY", "balanced")
        if policy not in {"balanced", "latency", "cost", "quality", "ordered"}:
            raise ConfigurationError(f"unsupported routing policy: {policy}")

        return cls(
            host=os.getenv("AGENTMESH_HOST", "127.0.0.1"),
            port=int(os.getenv("AGENTMESH_PORT", "8787")),
            routing_policy=policy,  # type: ignore[arg-type]
            max_attempts=max(1, int(os.getenv("AGENTMESH_MAX_ATTEMPTS", "3"))),
            failure_threshold=max(1, int(os.getenv("AGENTMESH_FAILURE_THRESHOLD", "3"))),
            cooldown_seconds=max(0.0, float(os.getenv("AGENTMESH_COOLDOWN_SECONDS", "30"))),
            gateway_token=os.getenv("AGENTMESH_GATEWAY_TOKEN"),
            providers=providers,
        )
