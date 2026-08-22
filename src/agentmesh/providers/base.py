from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from agentmesh.domain import NormalizedRequest, NormalizedResponse, StreamChunk


class Provider(Protocol):
    @property
    def name(self) -> str: ...

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse: ...

    def stream(self, request: NormalizedRequest) -> AsyncIterator[StreamChunk]: ...

    async def list_models(self) -> list[str]: ...
