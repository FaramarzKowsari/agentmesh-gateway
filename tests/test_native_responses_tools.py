from __future__ import annotations

import json

import httpx
import pytest

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider
from agentmesh.providers.openai_responses import OpenAIResponsesProvider
from agentmesh.protocols.responses_validation import SUPPORTED_TOOL_TYPES


@pytest.mark.parametrize(
    "tool_type",
    [
        "file_search",
        "computer",
        "computer_use_preview",
        "web_search",
        "web_search_2025_08_26",
        "mcp",
        "code_interpreter",
        "programmatic_tool_calling",
        "image_generation",
        "local_shell",
        "shell",
        "custom",
        "namespace",
        "tool_search",
        "web_search_preview",
        "apply_patch",
    ],
)
def test_public_sdk_native_tool_types_are_whitelisted(tool_type: str) -> None:
    assert tool_type in SUPPORTED_TOOL_TYPES


@pytest.mark.asyncio
async def test_native_tools_skip_translated_provider_and_preserve_wire_payload() -> None:
    captured: dict[str, object] = {}

    async def translated_handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("native Responses tools must not reach Chat Completions")

    async def native_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        payload = json.loads(request.content)
        captured["tools"] = payload["tools"]
        assert payload["tools"] == [
            {"type": "web_search_preview", "search_context_size": "low"},
            {"type": "local_shell"},
            {"type": "shell"},
            {"type": "apply_patch"},
        ]

        events = [
            {
                "type": "response.created",
                "response": {"id": "resp_tools", "model": "m", "status": "in_progress"},
            },
            {
                "type": "response.web_search_call.in_progress",
                "item_id": "ws_1",
                "output_index": 0,
            },
            {
                "type": "response.web_search_call.searching",
                "item_id": "ws_1",
                "output_index": 0,
            },
            {
                "type": "response.web_search_call.completed",
                "item_id": "ws_1",
                "output_index": 0,
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_tools",
                    "object": "response",
                    "model": "m",
                    "status": "completed",
                    "output": [
                        {
                            "type": "web_search_call",
                            "id": "ws_1",
                            "status": "completed",
                        }
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
        "input": "Use the available tools if needed.",
        "tools": [
            {"type": "web_search_preview", "search_context_size": "low"},
            {"type": "local_shell"},
            {"type": "shell"},
            {"type": "apply_patch"},
        ],
        "stream": True,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post("/v1/responses", json=request_payload)

    await translated_client.aclose()
    await native_client.aclose()

    assert response.status_code == 200
    assert captured["tools"] == request_payload["tools"]
    blocks = response.text.strip().split("\n\n")
    event_types = [
        next(line for line in block.splitlines() if line.startswith("event: ")).removeprefix(
            "event: "
        )
        for block in blocks
    ]
    assert event_types == [
        "response.created",
        "response.web_search_call.in_progress",
        "response.web_search_call.searching",
        "response.web_search_call.completed",
        "response.completed",
    ]


@pytest.mark.asyncio
async def test_function_tools_remain_eligible_for_cross_protocol_translation() -> None:
    calls = 0

    async def translated_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["tools"][0]["function"]["name"] == "lookup"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_1",
                "model": "m",
                "choices": [{"message": {"content": "ok"}}],
            },
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
    assert isinstance(translated, OpenAICompatibleProvider)
    translated_client = httpx.AsyncClient(transport=httpx.MockTransport(translated_handler))
    translated._client = translated_client

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "m",
                "input": "look it up",
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "parameters": {"type": "object"},
                    }
                ],
            },
        )

    await translated_client.aclose()

    assert response.status_code == 200
    assert calls == 1
    assert response.json()["output"][0]["content"][0]["text"] == "ok"
