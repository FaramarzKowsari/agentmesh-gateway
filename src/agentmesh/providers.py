"""HTTP adapters for supported upstream protocol families."""

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx

from .config import ProviderSettings
from .domain import CanonicalRequest, CanonicalResponse, ProviderFailure, ProviderMetadata


class HTTPProvider:
    def __init__(self, config: ProviderSettings, client: httpx.AsyncClient | None = None):
        self.config, self.name = config, config.name
        self.metadata = ProviderMetadata(config.priority, config.cost, config.latency, config.quality, tuple(config.models))
        self.client = client or httpx.AsyncClient(timeout=config.timeout_seconds)

    @property
    def headers(self) -> dict[str, str]:
        return {}

    async def health(self) -> bool:
        return True  # configured providers are ready; runtime failures feed the breaker

    async def stream(self, request: CanonicalRequest) -> AsyncIterator[str]:
        response = await self.complete(request)
        yield response.text

    async def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = await self.client.post(self.config.base_url.rstrip("/") + path, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderFailure(f"provider {self.name} failed") from exc


class OpenAIProvider(HTTPProvider):
    @property
    def headers(self) -> dict[str, str]:
        key = self.config.api_key.get_secret_value() if self.config.api_key else ""
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def complete(self, request: CanonicalRequest) -> CanonicalResponse:
        data = await self._post("/chat/completions", {"model": request.model, "messages": [m.model_dump() for m in request.messages]})
        try:
            text = data["choices"][0]["message"]["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderFailure("provider returned an invalid response") from exc
        return CanonicalResponse(id=str(data.get("id", uuid4())), model=request.model, text=str(text), provider=self.name)


class AnthropicProvider(HTTPProvider):
    @property
    def headers(self) -> dict[str, str]:
        key = self.config.api_key.get_secret_value() if self.config.api_key else ""
        return {"x-api-key": key, "anthropic-version": "2023-06-01"} if key else {"anthropic-version": "2023-06-01"}

    async def complete(self, request: CanonicalRequest) -> CanonicalResponse:
        data = await self._post("/messages", {"model": request.model, "messages": [m.model_dump() for m in request.messages], "max_tokens": request.max_tokens or 1024})
        try:
            text = data["content"][0]["text"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderFailure("provider returned an invalid response") from exc
        return CanonicalResponse(id=str(data.get("id", uuid4())), model=request.model, text=str(text), provider=self.name)
