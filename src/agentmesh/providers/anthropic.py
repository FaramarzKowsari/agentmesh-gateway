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

    @staticmethod
    def _arguments_object(arguments: str) -> object:
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {"raw": arguments}

    @classmethod
    def _message_payload(cls, message: Message) -> dict[str, object]:
        if message.tool_call_id:
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": message.tool_call_id,
                        "content": message.content,
                    }
                ],
            }

        role = message.role if message.role in {"user", "assistant"} else "user"
        if not message.tool_calls:
            return {"role": role, "content": message.content}

        blocks: list[dict[str, object]] = []
        if message.content:
            blocks.append({"type": "text", "text": message.content})
        blocks.extend(
            {
                "type": "tool_use",
                "id": call.call_id,
                "name": call.name,
                "input": cls._arguments_object(call.arguments),
            }
            for call in message.tool_calls
        )
        return {"role": "assistant", "content": blocks}

    @staticmethod
    def _tool_payload(tool: dict[str, object]) -> dict[str, object]:
        if tool.get("type") != "function":
            return dict(tool)
        if isinstance(tool.get("function"), dict):
            function = tool["function"]
            return {
                "name": function.get("name", ""),
                "description": function.get("description", ""),
                "input_schema": function.get("parameters", {"type": "object"}),
            }
        return {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "input_schema": tool.get("parameters", {"type": "object"}),
        }

    def _payload(self, request: NormalizedRequest, *, stream: bool) -> dict[str, object]:
        system_parts = [
            message.content for message in request.messages if message.role == "system"
        ]
        messages = [
            self._message_payload(message)
            for message in request.messages
            if message.role != "system"
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
            payload["tools"] = [self._tool_payload(tool) for tool in request.tools]
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
        content_blocks = data.get("content", [])
        text = "".join(
            str(block.get("text", ""))
            for block in content_blocks
            if block.get("type") == "text"
        )
        tool_calls = tuple(
            FunctionCall(
                call_id=str(block.get("id") or ""),
                name=str(block.get("name") or ""),
                arguments=json.dumps(
                    block.get("input") or {},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
            for block in content_blocks
            if block.get("type") == "tool_use"
        )
        usage = data.get("usage") or {}
        return NormalizedResponse(
            provider=self.name,
            model=str(data.get("model") or self._resolve_model(request.model)),
            content=text,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            raw_id=data.get("id"),
            tool_calls=tool_calls,
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
                    event_type = data.get("type")
                    if event_type == "content_block_start":
                        block = data.get("content_block") or {}
                        if block.get("type") != "tool_use":
                            continue
                        initial_input = block.get("input")
                        initial_arguments = ""
                        if initial_input not in (None, {}):
                            initial_arguments = json.dumps(
                                initial_input,
                                separators=(",", ":"),
                                sort_keys=True,
                            )
                        yield StreamChunk(
                            provider=self.name,
                            model=model,
                            function_call_delta=FunctionCallDelta(
                                index=int(data.get("index", 0)),
                                call_id=str(block.get("id") or ""),
                                name=str(block.get("name") or ""),
                                arguments_delta=initial_arguments,
                            ),
                        )
                    elif event_type == "content_block_delta":
                        delta = data.get("delta") or {}
                        if delta.get("type") == "input_json_delta":
                            yield StreamChunk(
                                provider=self.name,
                                model=model,
                                function_call_delta=FunctionCallDelta(
                                    index=int(data.get("index", 0)),
                                    arguments_delta=str(delta.get("partial_json") or ""),
                                ),
                            )
                            continue
                        text = delta.get("text") or ""
                        if text:
                            yield StreamChunk(
                                provider=self.name,
                                model=model,
                                text=str(text),
                            )
                    elif event_type == "message_stop":
                        yield StreamChunk(provider=self.name, model=model, done=True)
                        return
        except httpx.HTTPError as exc:
            raise translate_http_error(self.name, exc) from exc

    async def list_models(self) -> list[str]:
        return list(self.spec.models)
