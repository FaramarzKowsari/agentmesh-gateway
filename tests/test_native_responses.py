from __future__ import annotations

import json

import httpx
import pytest

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.domain import Message, NormalizedRequest, ResponsesControls
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider
from agentmesh.providers.openai_responses import OpenAIResponsesProvider


def _parse_sse(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for block in body.strip().split("\n\n"):
        data_line = next(line for line in block.splitlines() if line.startswith("data: "))
        events.append(json.loads(data_line.removeprefix("data: ")))
    return events


@pytest.mark.asyncio
async def test_reasoning_request_routes_only_to_native_responses_and_preserves_sse() -> None:
    captured: dict[str, object] = {}

    async def translated_handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("reasoning request must not reach Chat Completions adapter")

    async def native_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        payload = json.loads(request.content)
        captured["payload"] = payload

        assert payload["reasoning"] == {
            "effort": "high",
            "summary": "auto",
            "context": "all_turns",
        }
        assert payload["include"] == ["reasoning.encrypted_content"]
        assert payload["prompt_cache_key"] == "codex-session-1"
        assert payload["service_tier"] == "default"
        assert payload["text"] == {"verbosity": "medium"}
        assert payload["stream_options"] == {
            "reasoning_summary_delivery": "sequential_cutoff"
        }
        assert payload["client_metadata"] == {"surface": "codex"}
        assert payload["tool_choice"] == "auto"
        assert payload["parallel_tool_calls"] is False
        assert payload["store"] is False
        assert payload["input"][1]["type"] == "reasoning"
        assert payload["input"][1]["encrypted_content"] == "enc_previous"

        events = [
            {
                "type": "response.created",
                "response": {"id": "resp_native", "model": "m", "status": "in_progress"},
            },
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "type": "reasoning",
                    "id": "rs_1",
                    "encrypted_content": "enc_new",
                    "summary": [],
                },
            },
            {
                "type": "response.output_text.delta",
                "item_id": "msg_1",
                "output_index": 1,
                "content_index": 0,
                "delta": "NATIVE_OK",
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_native",
                    "object": "response",
                    "model": "m",
                    "status": "completed",
                    "output": [
                        {
                            "type": "reasoning",
                            "id": "rs_1",
                            "encrypted_content": "enc_new",
                            "summary": [],
                        },
                        {
                            "type": "message",
                            "id": "msg_1",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "NATIVE_OK",
                                    "annotations": [],
                                }
                            ],
                        },
                    ],
                },
            },
        ]
        body = "".join(
            f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
        )

    settings = Settings(
        routing_policy="ordered",
        providers=(
            ProviderSpec("translated", "openai", "http://translated/v1", ("m",)),
            ProviderSpec("native", "responses", "http://native/v1", ("m",)),
        ),
    )
    app = create_app(settings)
    translated = app.state.registry.get("translated")
    native = app.state.registry.get("native")
    assert isinstance(translated, OpenAICompatibleProvider)
    assert isinstance(native, OpenAIResponsesProvider)
    translated_client = httpx.AsyncClient(transport=httpx.MockTransport(translated_handler))
    native_client = httpx.AsyncClient(transport=httpx.MockTransport(native_handler))
    translated._client = translated_client
    native._client = native_client

    request_payload = {
        "model": "m",
        "instructions": "You are a coding agent.",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "continue"}],
            },
            {
                "type": "reasoning",
                "id": "rs_previous",
                "encrypted_content": "enc_previous",
                "summary": [],
            },
        ],
        "reasoning": {
            "effort": "high",
            "summary": "auto",
            "context": "all_turns",
        },
        "include": ["reasoning.encrypted_content"],
        "prompt_cache_key": "codex-session-1",
        "service_tier": "default",
        "text": {"verbosity": "medium"},
        "stream_options": {"reasoning_summary_delivery": "sequential_cutoff"},
        "client_metadata": {"surface": "codex"},
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "store": False,
        "stream": True,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post("/v1/responses", json=request_payload)

    await translated_client.aclose()
    await native_client.aclose()

    assert response.status_code == 200
    assert "payload" in captured
    events = _parse_sse(response.text)
    assert [event["type"] for event in events] == [
        "response.created",
        "response.output_item.added",
        "response.output_text.delta",
        "response.completed",
    ]
    reasoning_item = events[1]["item"]
    assert isinstance(reasoning_item, dict)
    assert reasoning_item["encrypted_content"] == "enc_new"
    completed = events[-1]["response"]
    assert isinstance(completed, dict)
    assert completed["output"][0]["encrypted_content"] == "enc_new"


@pytest.mark.asyncio
async def test_native_responses_nonstream_normalizes_text_and_function_calls() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        return httpx.Response(
            200,
            json={
                "id": "resp_1",
                "model": "m",
                "output": [
                    {"type": "reasoning", "id": "rs_1", "encrypted_content": "enc"},
                    {
                        "type": "message",
                        "id": "msg_1",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    },
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "lookup",
                        "arguments": "{\"q\":\"x\"}",
                    },
                ],
                "usage": {"input_tokens": 5, "output_tokens": 3},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIResponsesProvider(
        ProviderSpec("native", "responses", "http://native/v1", ("m",)),
        client,
    )
    request = NormalizedRequest(
        "m",
        (Message("user", "go"),),
        responses=ResponsesControls(raw_input="go", requires_native=True),
    )

    result = await provider.complete(request)
    await client.aclose()

    assert result.content == "done"
    assert result.tool_calls[0].call_id == "call_1"
    assert result.tool_calls[0].name == "lookup"
    assert result.input_tokens == 5
    assert result.output_tokens == 3
    assert result.native_responses is not None
    assert result.native_responses["output"][0]["encrypted_content"] == "enc"


@pytest.mark.asyncio
async def test_native_responses_stream_normalizes_function_argument_deltas() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        events = [
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": "",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "fc_1",
                "output_index": 0,
                "delta": "{\"q\":",
            },
            {
                "type": "response.function_call_arguments.delta",
                "item_id": "fc_1",
                "output_index": 0,
                "delta": "\"x\"}",
            },
            {"type": "response.completed", "response": {"id": "resp_1", "model": "m"}},
        ]
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAIResponsesProvider(
        ProviderSpec("native", "responses", "http://native/v1", ("m",)),
        client,
    )
    request = NormalizedRequest(
        "m",
        (Message("user", "go"),),
        stream=True,
        responses=ResponsesControls(raw_input="go", requires_native=True),
    )

    chunks = [chunk async for chunk in provider.stream(request)]
    await client.aclose()

    deltas = [chunk.function_call_delta for chunk in chunks if chunk.function_call_delta]
    assert deltas[0].call_id == "call_1"
    assert deltas[0].name == "lookup"
    assert "".join(delta.arguments_delta for delta in deltas) == "{\"q\":\"x\"}"
    assert chunks[-1].done is True
