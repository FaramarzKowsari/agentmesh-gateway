from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from agentmesh.config import ProviderSpec
from agentmesh.domain import Message, NormalizedRequest, NormalizedResponse, StreamChunk
from agentmesh.errors import ConfigurationError, NoProviderAvailable, ProviderError
from agentmesh.gateway.service import GatewayService
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Provider:
    def __init__(self, name: str, fail: bool = False) -> None:
        self._name = name
        self.fail = fail
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
        self.calls += 1
        if self.fail:
            raise ProviderError("temporary", provider=self.name, retryable=True, status_code=503)
        return NormalizedResponse(provider=self.name, model=request.model, content="ok")

    async def stream(self, request: NormalizedRequest) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        yield StreamChunk(provider=self.name, model=request.model, text="ok")
        yield StreamChunk(provider=self.name, model=request.model, done=True)

    async def list_models(self) -> list[str]:
        return ["m"]


class Registry:
    def __init__(self, providers: dict[str, Provider]) -> None:
        self.providers = providers

    def get(self, name: str) -> Provider:
        return self.providers[name]


def quota_spec(name: str = "limited", limit: int = 2, window: float = 60.0) -> ProviderSpec:
    return ProviderSpec(
        name,
        "openai",
        "http://example",
        ("m",),
        request_quota_limit=limit,
        request_quota_window_seconds=window,
    )


def test_quota_config_requires_complete_positive_pair() -> None:
    with pytest.raises(ConfigurationError, match="configured together"):
        ProviderSpec.from_dict(
            {
                "name": "x",
                "adapter": "openai",
                "base_url": "http://x",
                "models": ["m"],
                "request_quota_limit": 10,
            }
        )
    with pytest.raises(ConfigurationError, match="positive integer"):
        ProviderSpec.from_dict(
            {
                "name": "x",
                "adapter": "openai",
                "base_url": "http://x",
                "models": ["m"],
                "request_quota_limit": 0,
                "request_quota_window_seconds": 60,
            }
        )


def test_quota_pressure_exhaustion_and_reset_are_deterministic() -> None:
    clock = FakeClock()
    states = RuntimeStateStore(["limited"], clock=clock)
    Router((quota_spec(),), states, "ordered")

    initial = states.quota_snapshot("limited")
    assert initial["used"] == 0
    assert initial["pressure"] == 0.0
    assert initial["exhausted"] is False

    states.record_attempt("limited")
    first = states.quota_snapshot("limited")
    assert first["used"] == 1
    assert first["remaining"] == 1
    assert first["pressure"] == 0.5
    assert first["resets_in_seconds"] == 60.0

    states.record_attempt("limited")
    assert states.quota_exhausted("limited") is True
    assert states.quota_snapshot("limited")["pressure"] == 1.0

    clock.advance(60.0)
    reset = states.quota_snapshot("limited")
    assert reset["used"] == 0
    assert reset["remaining"] == 2
    assert reset["exhausted"] is False
    assert reset["resets_in_seconds"] is None


def test_router_excludes_exhausted_provider_before_scoring() -> None:
    clock = FakeClock()
    limited = quota_spec()
    fallback = ProviderSpec("fallback", "openai", "http://fallback", ("m",), cost_hint=1.0)
    states = RuntimeStateStore(["limited", "fallback"], clock=clock)
    router = Router((limited, fallback), states, "ordered")
    request = NormalizedRequest("m", (Message("user", "hi"),))

    assert [spec.name for spec in router.rank(request)] == ["limited", "fallback"]
    states.record_attempt("limited")
    states.record_attempt("limited")
    assert [spec.name for spec in router.rank(request)] == ["fallback"]


@pytest.mark.asyncio
async def test_failed_outbound_attempt_consumes_quota() -> None:
    clock = FakeClock()
    first = quota_spec("first", limit=1)
    second = ProviderSpec("second", "openai", "http://second", ("m",))
    states = RuntimeStateStore(["first", "second"], clock=clock)
    providers = {"first": Provider("first", fail=True), "second": Provider("second")}
    gateway = GatewayService(
        Registry(providers),  # type: ignore[arg-type]
        Router((first, second), states, "ordered"),
        states,
        max_attempts=2,
        failure_threshold=3,
        cooldown_seconds=30,
    )
    request = NormalizedRequest("m", (Message("user", "hi"),))

    response = await gateway.complete(request)
    assert response.provider == "second"
    assert states.quota_snapshot("first")["used"] == 1
    assert states.quota_exhausted("first") is True
    assert providers["first"].calls == 1

    response = await gateway.complete(request)
    assert response.provider == "second"
    assert providers["first"].calls == 1


@pytest.mark.asyncio
async def test_single_provider_returns_unavailable_after_quota_exhaustion() -> None:
    clock = FakeClock()
    spec = quota_spec(limit=1)
    states = RuntimeStateStore(["limited"], clock=clock)
    provider = Provider("limited")
    gateway = GatewayService(
        Registry({"limited": provider}),  # type: ignore[arg-type]
        Router((spec,), states, "ordered"),
        states,
        max_attempts=1,
        failure_threshold=3,
        cooldown_seconds=30,
    )
    request = NormalizedRequest("m", (Message("user", "hi"),))

    await gateway.complete(request)
    with pytest.raises(NoProviderAvailable):
        await gateway.complete(request)
