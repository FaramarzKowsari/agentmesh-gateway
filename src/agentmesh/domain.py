"""Canonical, provider-neutral domain objects."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field


class CanonicalMessage(BaseModel):
    role: str
    content: str


class CanonicalRequest(BaseModel):
    model: str
    messages: list[CanonicalMessage]
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = None
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalResponse(BaseModel):
    id: str
    model: str
    text: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


class GatewayError(Exception):
    """Safe normalized error, suitable for returning to clients."""

    def __init__(self, message: str, *, code: str = "upstream_error", status: int = 502):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


class ProviderFailure(Exception):
    """Internal upstream failure. Its raw text must not cross the API boundary."""


@dataclass(frozen=True)
class ProviderMetadata:
    priority: int = 100
    cost: float = 1.0
    latency: float = 1.0
    quality: float = 1.0
    models: tuple[str, ...] = field(default_factory=tuple)


class Provider(Protocol):
    name: str
    metadata: ProviderMetadata

    async def complete(self, request: CanonicalRequest) -> CanonicalResponse: ...

    async def stream(self, request: CanonicalRequest) -> AsyncIterator[str]: ...

    async def health(self) -> bool: ...


def normalize_error(exc: Exception) -> GatewayError:
    """Map internal exceptions without exposing URLs, credentials, or response bodies."""
    if isinstance(exc, GatewayError):
        return exc
    return GatewayError("All eligible providers failed", code="providers_unavailable", status=503)
