from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

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


class OpenAIResponsesProvider:
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
    def _message_item(message: Message) -> dict[str, Any]:
        part_type = "output_text" if message.role == "assistant" else "input_text"
        return {
            "type": "message",
            "role": message.role,
            "content": [{"type": part_type, "text": message.content}],
        }

    @classmethod
    def _synthesized_input(cls, request: NormalizedRequest) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            if message.tool_call_id:
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )
                continue
            if message.content:
                items.append(cls._message_item(message))
            for call in message.tool_calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                )
        return items

    @staticmethod
    def _system_instructions(request: NormalizedRequest) -> str | None:
        parts = [message.content for message in request.messages if message.role == "system"]
        return "\n\n".join(parts) if parts else None

    def _payload(self, request: NormalizedRequest, *, stream: bool) -> dict[str, Any]:
        controls = request.responses
        raw_input = controls.raw_input if controls is not None else None
        if isinstance(raw_input, (str, list)):
            input_value: object = raw_input
        else:
            input_value = self._synthesized_input(request)

        payload: dict[str, Any] = {
            "model": self._resolve_model(request.model),
            "input": input_value,
            "stream": stream,
        }
        instructions = controls.instructions if controls is not None else None
        instructions = instructions or self._system_instructions(request)
        if instructions:
            payload["instructions"] = instructions
        if request.tools:
            payload["tools"] = [dict(tool) for tool in request.tools]
        if request.max_tokens is not None:
            payload["max_output_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.metadata:
            payload["metadata"] = dict(request.metadata)

        if controls is not None:
            if controls.reasoning is not None:
                payload["reasoning"] = controls.reasoning.as_dict()
            if controls.include:
                payload["include"] = list(controls.include)
            if controls.prompt_cache_key is not None:
                payload["prompt_cache_key"] = controls.prompt_cache_key
            if controls.service_tier is not None:
                payload["service_tier"] = controls.service_tier
            if controls.text is not None:
                payload["text"] = dict(controls.text)
            if controls.stream_options is not None:
                payload["stream_options"] = dict(controls.stream_options)
            if controls.client_metadata is not None:
                payload["client_metadata"] = dict(controls.client_metadata)
            if controls.tool_choice is not None:
                payload["tool_choice"] = controls.tool_choice
            if controls.parallel_tool_calls is not None:
                payload["parallel_tool_calls"] = controls.parallel_tool_calls
            if controls.store is not None:
                payload["store"] = controls.store
        return payload

    @staticmethod
    def _normalized_output(data: dict[str, Any]) -> tuple[str, tuple[FunctionCall, ...]]:
        texts: list[str] = []
        calls: list[FunctionCall] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "output_text":
                        texts.append(str(part.get("text") or ""))
            elif item.get("type") == "function_call":
                calls.append(
                    FunctionCall(
                        call_id=str(item.get("call_id") or item.get("id") or ""),
                        name=str(item.get("name") or ""),
                        arguments=str(item.get("arguments") or "{}"),
                    )
                )
        return "".join(texts), tuple(calls)

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
        try:
            response = await self._client.post(
                f"{self.spec.base_url}/responses",
                headers=self._headers(),
                json=self._payload(request, stream=False),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise translate_http_error(self.name, exc) from exc

        data = response.json()
        content, tool_calls = self._normalized_output(data)
        usage = data.get("usage") or {}
        return NormalizedResponse(
            provider=self.name,
            model=str(data.get("model") or self._resolve_model(request.model)),
            content=content,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            raw_id=data.get("id"),
            tool_calls=tool_calls,
            native_responses=data,
        )

    async def stream(self, request: NormalizedRequest) -> AsyncIterator[StreamChunk]:
        model = self._resolve_model(request.model)
        calls: dict[str, tuple[int, str | None, str | None]] = {}
        try:
            async with self._client.stream(
                "POST",
                f"{self.spec.base_url}/responses",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body or body == "[DONE]":
                        continue
                    event = json.loads(body)
                    event_type = event.get("type")
                    event_model = model
                    response_body = event.get("response")
                    if isinstance(response_body, dict) and response_body.get("model"):
                        event_model = str(response_body["model"])

                    text = ""
                    function_delta = None
                    done = event_type == "response.completed"
                    if event_type == "response.output_text.delta":
                        text = str(event.get("delta") or "")
                    elif event_type == "response.output_item.added":
                        item = event.get("item") or {}
                        if isinstance(item, dict) and item.get("type") == "function_call":
                            item_id = str(item.get("id") or "")
                            index = int(event.get("output_index") or 0)
                            call_id = str(item.get("call_id") or "") or None
                            name = str(item.get("name") or "") or None
                            calls[item_id] = (index, call_id, name)
                            function_delta = FunctionCallDelta(
                                index=index,
                                call_id=call_id,
                                name=name,
                            )
                    elif event_type == "response.function_call_arguments.delta":
                        item_id = str(event.get("item_id") or "")
                        index, call_id, name = calls.get(
                            item_id,
                            (int(event.get("output_index") or 0), None, None),
                        )
                        function_delta = FunctionCallDelta(
                            index=index,
                            call_id=call_id,
                            name=name,
                            arguments_delta=str(event.get("delta") or ""),
                        )

                    yield StreamChunk(
                        provider=self.name,
                        model=event_model,
                        text=text,
                        done=done,
                        function_call_delta=function_delta,
                        native_responses_event=event,
                    )
        except httpx.HTTPError as exc:
            raise translate_http_error(self.name, exc) from exc

    async def list_models(self) -> list[str]:
        return list(self.spec.models)
