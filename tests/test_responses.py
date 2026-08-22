from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from agentmesh.domain import NormalizedResponse, StreamChunk
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


async def response_chunks() -> AsyncIterator[StreamChunk]:
    yield StreamChunk(provider="p", model="resolved-model", text="hel")
    yield StreamChunk(provider="p", model="resolved-model", text="lo")
    yield StreamChunk(provider="p", model="resolved-model", text="", done=True)


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


def test_unknown_nonstream_usage_is_not_fabricated() -> None:
    body = render_responses_response(
        NormalizedResponse(provider="p", model="m", content="answer")
    )

    assert body["usage"] is None
