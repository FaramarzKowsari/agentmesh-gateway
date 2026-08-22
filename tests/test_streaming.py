from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from agentmesh.config import ProviderSpec
from agentmesh.domain import Message, NormalizedRequest, NormalizedResponse, StreamChunk
from agentmesh.errors import ProviderError
from agentmesh.gateway.service import GatewayService
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore


class StreamProvider:
    def __init__(self, name: str, behavior: str) -> None:
        self._name = name
        self.behavior = behavior
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
        return NormalizedResponse(provider=self.name, model=request.model, content="unused")

    async def stream(self, request: NormalizedRequest) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        if self.behavior == "fail-before":
            raise ProviderError("temporary", provider=self.name, retryable=True)
        if self.behavior == "fail-after":
            yield StreamChunk(provider=self.name, model=request.model, text="partial")
            raise ProviderError("temporary", provider=self.name, retryable=True)
        yield StreamChunk(provider=self.name, model=request.model, text="ok")
        yield StreamChunk(provider=self.name, model=request.model, text="", done=True)

    async def list_models(self) -> list[str]:
        return ["m"]


class Registry:
    def __init__(self, providers: dict[str, StreamProvider]) -> None:
        self.providers = providers

    def get(self, name: str) -> StreamProvider:
        return self.providers[name]


def gateway(first: StreamProvider, second: StreamProvider) -> GatewayService:
    specs = (
        ProviderSpec("first", "openai", "http://one", ("m",)),
        ProviderSpec("second", "openai", "http://two", ("m",)),
    )
    states = RuntimeStateStore(["first", "second"])
    return GatewayService(
        Registry({"first": first, "second": second}),  # type: ignore[arg-type]
        Router(specs, states, "ordered"),
        states,
        max_attempts=2,
        failure_threshold=3,
        cooldown_seconds=30,
    )


def request() -> NormalizedRequest:
    return NormalizedRequest("m", (Message("user", "hello"),), stream=True)


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_committed_chunk() -> None:
    first = StreamProvider("first", "fail-before")
    second = StreamProvider("second", "ok")
    service = gateway(first, second)

    chunks = [chunk async for chunk in service.stream(request())]

    assert [chunk.text for chunk in chunks] == ["ok", ""]
    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_stream_does_not_fallback_after_first_committed_chunk() -> None:
    first = StreamProvider("first", "fail-after")
    second = StreamProvider("second", "ok")
    service = gateway(first, second)

    seen: list[str] = []
    with pytest.raises(ProviderError):
        async for chunk in service.stream(request()):
            seen.append(chunk.text)

    assert seen == ["partial"]
    assert first.calls == 1
    assert second.calls == 0
