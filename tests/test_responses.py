from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from agentmesh.domain import (
    FunctionCall,
    FunctionCallDelta,
    NormalizedResponse,
    StreamChunk,
)
from agentmesh.protocols.responses import (
    parse_responses_request,
    render_responses_response,
    render_responses_stream,
)


def test_parse_responses_string_input() -> None:
    request = parse_responses_request(
        {"model": "auto", "instructions": "be brief", "input": "hello"}
    )
    assert request.messages[0].role == "system"
    assert request.messages[1].content == "hello"


def test_parse_responses_item_input() -> None:
    request = parse_responses_request(
        {
            "model": "m",
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                }
            ],
        }
    )
    assert request.messages[0].content == "hello"


def test_parse_responses_function_call_and_output_items() -> None:
    request = parse_responses_request(
        {
            "model": "m",
            "input": [
                {
                    "type": "function_call",
                    "call_id": "call_123",
                    "name": "get_weather",
                    "arguments": "{\"city\":\"Istanbul\"}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": {"temperature": 24},
                },
            ],
        }
    )

    assistant = request.messages[0]
    assert assistant.role == "assistant"
    assert assistant.tool_calls[0].call_id == "call_123"
    assert assistant.tool_calls[0].name == "get_weather"
    assert assistant.tool_calls[0].arguments == "{\"city\":\"Istanbul\"}"

    tool_result = request.messages[1]
    assert tool_result.role == "tool"
    assert tool_result.tool_call_id == "call_123"
    assert tool_result.content == "{\"temperature\":24}"


def test_render_responses_response() -> None:
    body = render_responses_response(
        NormalizedResponse(
            provider="p",
            model="m",
            content="answer",
            input_tokens=2,
            output_tokens=3,
        )
    )
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output"][0]["content"][0]["text"] == "answer"
    assert body["usage"]["total_tokens"] == 5


def test_render_responses_function_call_output_item() -> None:
    body = render_responses_response(
        NormalizedResponse(
            provider="p",
            model="m",
            content="",
            tool_calls=(
                FunctionCall(
                    call_id="call_123",
                    name="get_weather",
                    arguments="{\"city\":\"Istanbul\"}",
                ),
            ),
        )
    )

    assert len(body["output"]) == 1
    call = body["output"][0]
    assert call["type"] == "function_call"
    assert call["call_id"] == "call_123"
    assert call["name"] == "get_weather"
    assert call["arguments"] == "{\"city\":\"Istanbul\"}"
    assert call["status"] == "completed"


async def response_chunks() -> AsyncIterator[StreamChunk]:
    yield StreamChunk(provider="p", model="resolved-model", text="hel")
    yield StreamChunk(provider="p", model="resolved-model", text="lo")
    yield StreamChunk(provider="p", model="resolved-model", done=True)


async def function_call_chunks() -> AsyncIterator[StreamChunk]:
    yield StreamChunk(
        provider="p",
        model="resolved-model",
        function_call_delta=FunctionCallDelta(
            index=0,
            call_id="call_123",
            name="get_weather",
            arguments_delta="{\"city\":\"",
        ),
    )
    yield StreamChunk(
        provider="p",
        model="resolved-model",
        function_call_delta=FunctionCallDelta(
            index=0,
            arguments_delta="Istanbul\"}",
        ),
    )
    yield StreamChunk(provider="p", model="resolved-model", done=True)


def parse_sse_event(raw: str) -> tuple[str, dict[str, object]]:
    lines = raw.strip().splitlines()
    event_type = lines[0].removeprefix("event: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    return event_type, payload


@pytest.mark.asyncio
async def test_responses_stream_has_complete_text_lifecycle() -> None:
    raw_events = [event async for event in render_responses_stream(response_chunks(), "auto")]
    events = [parse_sse_event(event) for event in raw_events]

    assert [event_type for event_type, _ in events] == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]
    assert [payload["sequence_number"] for _, payload in events] == list(range(10))

    created = events[0][1]["response"]
    assert isinstance(created, dict)
    assert created["status"] == "in_progress"
    assert created["usage"] is None

    completed = events[-1][1]["response"]
    assert isinstance(completed, dict)
    assert completed["status"] == "completed"
    assert completed["model"] == "resolved-model"
    assert completed["provider"] == "p"
    assert completed["usage"] is None
    assert completed["output"][0]["content"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_responses_stream_has_complete_function_call_lifecycle() -> None:
    raw_events = [
        event async for event in render_responses_stream(function_call_chunks(), "auto")
    ]
    events = [parse_sse_event(event) for event in raw_events]

    assert [event_type for event_type, _ in events] == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.output_item.done",
        "response.completed",
    ]
    assert [payload["sequence_number"] for _, payload in events] == list(range(8))

    added = events[2][1]["item"]
    assert isinstance(added, dict)
    assert added["type"] == "function_call"
    assert added["call_id"] == "call_123"
    assert added["name"] == "get_weather"
    assert added["arguments"] == ""
    assert added["status"] == "in_progress"

    arguments_done = events[5][1]
    assert arguments_done["name"] == "get_weather"
    assert arguments_done["arguments"] == "{\"city\":\"Istanbul\"}"

    completed = events[-1][1]["response"]
    assert isinstance(completed, dict)
    call = completed["output"][0]
    assert call["type"] == "function_call"
    assert call["call_id"] == "call_123"
    assert call["name"] == "get_weather"
    assert call["arguments"] == "{\"city\":\"Istanbul\"}"
    assert call["status"] == "completed"


def test_unknown_nonstream_usage_is_not_fabricated() -> None:
    body = render_responses_response(
        NormalizedResponse(provider="p", model="m", content="answer")
    )

    assert body["usage"] is None
