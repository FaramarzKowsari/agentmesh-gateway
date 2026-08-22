from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from agentmesh.config import ProviderSpec
from agentmesh.domain import Message, NormalizedRequest, NormalizedResponse, StreamChunk
from agentmesh.errors import ProviderError
from agentmesh.gateway.service import GatewayService
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore


class FakeProvider:
    def __init__(self, name: str, *, fail: bool = False) -> None:
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
        if self.fail:
            raise ProviderError("temporary", provider=self.name, retryable=True)
        yield StreamChunk(provider=self.name, model=request.model, text="ok")
        yield StreamChunk(provider=self.name, model=request.model, text="", done=True)

    async def list_models(self) -> list[str]:
        return ["m"]


class FakeRegistry:
    def __init__(self, providers: dict[str, FakeProvider]) -> None:
        self.providers = providers

    def get(self, name: str) -> FakeProvider:
        return self.providers[name]


@pytest.mark.asyncio
async def test_fallback_uses_second_provider() -> None:
    specs = (
        ProviderSpec("first", "openai", "http://one", ("m",)),
        ProviderSpec("second", "openai", "http://two", ("m",)),
    )
    states = RuntimeStateStore(["first", "second"])
    router = Router(specs, states, "ordered")
    providers = {"first": FakeProvider("first", fail=True), "second": FakeProvider("second")}
    gateway = GatewayService(
        FakeRegistry(providers),  # type: ignore[arg-type]
        router,
        states,
        max_attempts=2,
        failure_threshold=3,
        cooldown_seconds=30,
    )
    request = NormalizedRequest("m", (Message("user", "hi"),))
    response = await gateway.complete(request)
    assert response.provider == "second"
    assert providers["first"].calls == 1
    assert providers["second"].calls == 1


@pytest.mark.asyncio
async def test_terminal_error_does_not_fallback() -> None:
    class Terminal(FakeProvider):
        async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
            raise ProviderError("bad request", provider=self.name, retryable=False, status_code=400)

    specs = (
        ProviderSpec("first", "openai", "http://one", ("m",)),
        ProviderSpec("second", "openai", "http://two", ("m",)),
    )
    states = RuntimeStateStore(["first", "second"])
    gateway = GatewayService(
        FakeRegistry({"first": Terminal("first"), "second": FakeProvider("second")}),  # type: ignore[arg-type]
        Router(specs, states, "ordered"),
        states,
        max_attempts=2,
        failure_threshold=3,
        cooldown_seconds=30,
    )
    request = NormalizedRequest("m", (Message("user", "hi"),))
    with pytest.raises(ProviderError) as caught:
        await gateway.complete(request)
    assert caught.value.status_code == 400
