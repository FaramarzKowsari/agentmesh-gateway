from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

from agentmesh.config import ProviderSpec
from agentmesh.domain import (
    FunctionCall,
    FunctionCallDelta,
    Message,
    NormalizedRequest,
    NormalizedResponse,
    StreamChunk,
)
from agentmesh.providers.http_errors import translate_http_error


class OpenAICompatibleProvider:
    def __init__(self, spec: ProviderSpec, client: httpx.AsyncClient | None = None) -> None:
        self.spec = spec
        self._client = client or httpx.AsyncClient(timeout=spec.timeout_seconds)

    @property
    def name(self) -> str:
        return self.spec.name

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.spec.api_key_env:
            token = os.getenv(self.spec.api_key_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _resolve_model(self, requested: str) -> str:
        if requested != "auto" and requested in self.spec.models:
            return requested
        return self.spec.models[0]

    @staticmethod
    def _message_payload(message: Message) -> dict[str, object]:
        payload: dict[str, object] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            payload["content"] = message.content or None
            payload["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        return payload

    @staticmethod
    def _tool_payload(tool: dict[str, object]) -> dict[str, object]:
        if tool.get("type") != "function" or "function" in tool:
            return dict(tool)
        function = {
            key: tool[key]
            for key in ("name", "description", "parameters", "strict")
            if key in tool
        }
        return {"type": "function", "function": function}

    def _payload(self, request: NormalizedRequest, *, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self._resolve_model(request.model),
            "messages": [self._message_payload(message) for message in request.messages],
            "stream": stream,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = [self._tool_payload(tool) for tool in request.tools]
        return payload

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
        try:
            response = await self._client.post(
                f"{self.spec.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request, stream=False),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise translate_http_error(self.name, exc) from exc
        data = response.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        tool_calls: list[FunctionCall] = []
        for item in message.get("tool_calls") or []:
            function = item.get("function") or {}
            arguments = function.get("arguments") or "{}"
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, separators=(",", ":"), sort_keys=True)
            tool_calls.append(
                FunctionCall(
                    call_id=str(item.get("id") or ""),
                    name=str(function.get("name") or ""),
                    arguments=arguments,
                )
            )
        usage = data.get("usage") or {}
        return NormalizedResponse(
            provider=self.name,
            model=str(data.get("model") or self._resolve_model(request.model)),
            content=str(content),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            raw_id=data.get("id"),
            tool_calls=tuple(tool_calls),
        )

    async def stream(self, request: NormalizedRequest) -> AsyncIterator[StreamChunk]:
        model = self._resolve_model(request.model)
        try:
            async with self._client.stream(
                "POST",
                f"{self.spec.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        yield StreamChunk(provider=self.name, model=model, done=True)
                        return
                    if not body:
                        continue
                    data = json.loads(body)
                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    text = delta.get("content") or ""
                    if text:
                        yield StreamChunk(provider=self.name, model=model, text=str(text))
                    for call in delta.get("tool_calls") or []:
                        function = call.get("function") or {}
                        call_id = call.get("id")
                        name = function.get("name")
                        arguments = function.get("arguments") or ""
                        yield StreamChunk(
                            provider=self.name,
                            model=model,
                            function_call_delta=FunctionCallDelta(
                                index=int(call.get("index", 0)),
                                call_id=str(call_id) if call_id is not None else None,
                                name=str(name) if name is not None else None,
                                arguments_delta=str(arguments),
                            ),
                        )
        except httpx.HTTPError as exc:
            raise translate_http_error(self.name, exc) from exc

    async def list_models(self) -> list[str]:
        return list(self.spec.models)
