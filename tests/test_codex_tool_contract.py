from __future__ import annotations

import json

import httpx
import pytest

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider


def _parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        events.append(
            (
                event_line.removeprefix("event: "),
                json.loads(data_line.removeprefix("data: ")),
            )
        )
    return events


def _function_tool() -> dict[str, object]:
    return {
        "type": "function",
        "name": "read_file",
        "description": "Read a local file by path.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    }


@pytest.mark.asyncio
async def test_codex_streamed_function_call_and_output_continuation() -> None:
    upstream_requests: list[dict[str, object]] = []

    async def upstream_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        upstream_requests.append(payload)
        assert request.url.path == "/v1/chat/completions"
        assert payload["stream"] is True

        if len(upstream_requests) == 1:
            assert payload["messages"] == [
                {"role": "system", "content": "You are a coding agent."},
                {"role": "user", "content": "Read README.md, then report success."},
            ]
            assert payload["tools"][0]["function"]["name"] == "read_file"
            stream = "".join(
                [
                    'data: {"model":"m","choices":[{"delta":{"tool_calls":['
                    '{"index":0,"id":"call_read_1","type":"function",'
                    '"function":{"name":"read_file","arguments":"{\\"path\\":\\""}}]}}]}\n\n',
                    'data: {"model":"m","choices":[{"delta":{"tool_calls":['
                    '{"index":0,"function":{"arguments":"README.md\\"}"}}]}}]}\n\n',
                    "data: [DONE]\n\n",
                ]
            )
        else:
            assert len(upstream_requests) == 2
            messages = payload["messages"]
            assert messages[0] == {
                "role": "system",
                "content": "You are a coding agent.",
            }
            assert messages[1]["role"] == "assistant"
            assert messages[1]["content"] is None
            assert messages[1]["tool_calls"] == [
                {
                    "id": "call_read_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"README.md"}',
                    },
                }
            ]
            assert messages[2] == {
                "role": "tool",
                "content": "file contents",
                "tool_call_id": "call_read_1",
            }
            stream = "".join(
                [
                    'data: {"model":"m","choices":[{"delta":'
                    '{"content":"TOOL_TURN_"}}]}\n\n',
                    'data: {"model":"m","choices":[{"delta":'
                    '{"content":"OK"}}]}\n\n',
                    "data: [DONE]\n\n",
                ]
            )

        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=stream,
        )

    settings = Settings(
        providers=(
            ProviderSpec(
                name="mock",
                adapter="openai",
                base_url="http://upstream/v1",
                models=("m",),
            ),
        )
    )
    app = create_app(settings)
    provider = app.state.registry.get("mock")
    assert isinstance(provider, OpenAICompatibleProvider)
    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    provider._client = upstream_client

    first_payload = {
        "model": "m",
        "instructions": "You are a coding agent.",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Read README.md, then report success.",
                    }
                ],
            }
        ],
        "tools": [_function_tool()],
        "stream": True,
        "store": False,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://agentmesh",
    ) as client:
        first_response = await client.post("/v1/responses", json=first_payload)
        assert first_response.status_code == 200
        first_events = _parse_sse(first_response.text)
        assert [event_type for event_type, _ in first_events] == [
            "response.created",
            "response.in_progress",
            "response.output_item.added",
            "response.function_call_arguments.delta",
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
            "response.output_item.done",
            "response.completed",
        ]

        first_completed = first_events[-1][1]["response"]
        assert isinstance(first_completed, dict)
        call = first_completed["output"][0]
        assert call["type"] == "function_call"
        assert call["call_id"] == "call_read_1"
        assert call["name"] == "read_file"
        assert call["arguments"] == '{"path":"README.md"}'

        second_payload = {
            "model": "m",
            "instructions": "You are a coding agent.",
            "input": [
                {
                    "type": "function_call",
                    "call_id": call["call_id"],
                    "name": call["name"],
                    "arguments": call["arguments"],
                },
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": "file contents",
                },
            ],
            "tools": [_function_tool()],
            "stream": True,
            "store": False,
        }
        second_response = await client.post("/v1/responses", json=second_payload)

    await upstream_client.aclose()

    assert second_response.status_code == 200
    second_events = _parse_sse(second_response.text)
    second_completed = second_events[-1][1]["response"]
    assert isinstance(second_completed, dict)
    assert second_completed["output"][0]["content"][0]["text"] == "TOOL_TURN_OK"
    assert len(upstream_requests) == 2
