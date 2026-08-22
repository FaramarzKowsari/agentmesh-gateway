from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

from agentmesh.config import ProviderSpec
from agentmesh.domain import NormalizedRequest, NormalizedResponse, StreamChunk
from agentmesh.providers.http_errors import translate_http_error


class AnthropicProvider:
    def __init__(self, spec: ProviderSpec, client: httpx.AsyncClient | None = None) -> None:
        self.spec = spec
        self._client = client or httpx.AsyncClient(timeout=spec.timeout_seconds)

    @property
    def name(self) -> str:
        return self.spec.name

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if self.spec.api_key_env:
            key = os.getenv(self.spec.api_key_env)
            if key:
                headers["x-api-key"] = key
        return headers

    def _resolve_model(self, requested: str) -> str:
        if requested != "auto" and requested in self.spec.models:
            return requested
        return self.spec.models[0]

    def _payload(self, request: NormalizedRequest, *, stream: bool) -> dict[str, object]:
        system_parts = [m.content for m in request.messages if m.role == "system"]
        messages = [
            {"role": m.role if m.role in {"user", "assistant"} else "user", "content": m.content}
            for m in request.messages
            if m.role != "system"
        ]
        payload: dict[str, object] = {
            "model": self._resolve_model(request.model),
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "stream": stream,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = list(request.tools)
        return payload

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
        try:
            response = await self._client.post(
                f"{self.spec.base_url}/v1/messages",
                headers=self._headers(),
                json=self._payload(request, stream=False),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise translate_http_error(self.name, exc) from exc
        data = response.json()
        text = "".join(
            str(block.get("text", ""))
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return NormalizedResponse(
            provider=self.name,
            model=str(data.get("model") or self._resolve_model(request.model)),
            content=text,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            raw_id=data.get("id"),
        )

    async def stream(self, request: NormalizedRequest) -> AsyncIterator[StreamChunk]:
        model = self._resolve_model(request.model)
        try:
            async with self._client.stream(
                "POST",
                f"{self.spec.base_url}/v1/messages",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body:
                        continue
                    data = json.loads(body)
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta") or {}
                        text = delta.get("text") or ""
                        if text:
                            yield StreamChunk(provider=self.name, model=model, text=str(text))
                    elif data.get("type") == "message_stop":
                        yield StreamChunk(provider=self.name, model=model, text="", done=True)
                        return
        except httpx.HTTPError as exc:
            raise translate_http_error(self.name, exc) from exc

    async def list_models(self) -> list[str]:
        return list(self.spec.models)
