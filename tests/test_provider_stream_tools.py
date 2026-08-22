from __future__ import annotations

import httpx
import pytest

from agentmesh.config import ProviderSpec
from agentmesh.domain import FunctionCallDelta, Message, NormalizedRequest
from agentmesh.providers.anthropic import AnthropicProvider
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider


def streaming_request() -> NormalizedRequest:
    return NormalizedRequest(
        model="m",
        messages=(Message("user", "use the lookup tool"),),
        stream=True,
        tools=(
            {
                "type": "function",
                "name": "lookup",
                "description": "Look up a value",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                },
            },
        ),
    )


@pytest.mark.asyncio
async def test_openai_stream_normalizes_function_call_deltas() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        body = "".join(
            [
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
                '"id":"call_1","type":"function","function":'
                '{"name":"lookup","arguments":"{\\"q\\":\\""}}]}}]}\n\n',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
                '"function":{"arguments":"x\\"}"}}]}}]}\n\n',
                "data: [DONE]\n\n",
            ]
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        ProviderSpec("p", "openai", "http://provider/v1", ("m",)),
        client,
    )

    chunks = [chunk async for chunk in provider.stream(streaming_request())]

    assert chunks[0].function_call_delta == FunctionCallDelta(
        index=0,
        call_id="call_1",
        name="lookup",
        arguments_delta='{"q":"',
    )
    assert chunks[1].function_call_delta == FunctionCallDelta(
        index=0,
        arguments_delta='x"}',
    )
    assert chunks[2].done is True
    await client.aclose()


@pytest.mark.asyncio
async def test_anthropic_stream_normalizes_tool_use_deltas() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        body = "".join(
            [
                'data: {"type":"content_block_start","index":0,'
                '"content_block":{"type":"tool_use","id":"call_1",'
                '"name":"lookup","input":{}}}\n\n',
                'data: {"type":"content_block_delta","index":0,'
                '"delta":{"type":"input_json_delta",'
                '"partial_json":"{\\"q\\":\\"x\\"}"}}\n\n',
                'data: {"type":"message_stop"}\n\n',
            ]
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AnthropicProvider(
        ProviderSpec("a", "anthropic", "http://provider", ("m",)),
        client,
    )

    chunks = [chunk async for chunk in provider.stream(streaming_request())]

    assert chunks[0].function_call_delta == FunctionCallDelta(
        index=0,
        call_id="call_1",
        name="lookup",
    )
    assert chunks[1].function_call_delta == FunctionCallDelta(
        index=0,
        arguments_delta='{"q":"x"}',
    )
    assert chunks[2].done is True
    await client.aclose()
