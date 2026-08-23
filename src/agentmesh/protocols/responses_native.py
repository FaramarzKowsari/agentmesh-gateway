from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from agentmesh.domain import (
    NormalizedRequest,
    NormalizedResponse,
    ReasoningControls,
    ResponsesControls,
    StreamChunk,
)
from agentmesh.protocols.responses import render_responses_response, render_responses_stream


def _reasoning_controls(value: object) -> ReasoningControls | None:
    if not isinstance(value, dict):
        return None
    return ReasoningControls(
        effort=value.get("effort") if isinstance(value.get("effort"), str) else None,
        summary=value.get("summary") if isinstance(value.get("summary"), str) else None,
        context=value.get("context") if isinstance(value.get("context"), str) else None,
    )


def _has_native_input_item(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return any(isinstance(item, dict) and item.get("type") == "reasoning" for item in value)


def attach_responses_controls(
    request: NormalizedRequest,
    payload: dict[str, Any],
) -> NormalizedRequest:
    reasoning = _reasoning_controls(payload.get("reasoning"))
    include = tuple(str(item) for item in payload.get("include") or ())
    text = payload.get("text") if isinstance(payload.get("text"), dict) else None
    stream_options = (
        payload.get("stream_options") if isinstance(payload.get("stream_options"), dict) else None
    )
    client_metadata = (
        payload.get("client_metadata") if isinstance(payload.get("client_metadata"), dict) else None
    )
    prompt_cache_key = payload.get("prompt_cache_key")
    service_tier = payload.get("service_tier")
    tool_choice = payload.get("tool_choice")
    parallel_tool_calls = payload.get("parallel_tool_calls")
    store = payload.get("store")

    requires_native = any(
        (
            reasoning is not None,
            bool(include),
            isinstance(prompt_cache_key, str),
            isinstance(service_tier, str),
            text is not None,
            stream_options is not None,
            client_metadata is not None,
            tool_choice is not None,
            isinstance(parallel_tool_calls, bool),
            isinstance(store, bool),
            _has_native_input_item(payload.get("input")),
        )
    )

    controls = ResponsesControls(
        instructions=(
            payload.get("instructions") if isinstance(payload.get("instructions"), str) else None
        ),
        reasoning=reasoning,
        include=include,
        prompt_cache_key=prompt_cache_key if isinstance(prompt_cache_key, str) else None,
        service_tier=service_tier if isinstance(service_tier, str) else None,
        text=dict(text) if text is not None else None,
        stream_options=dict(stream_options) if stream_options is not None else None,
        client_metadata=dict(client_metadata) if client_metadata is not None else None,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls if isinstance(parallel_tool_calls, bool) else None,
        store=store if isinstance(store, bool) else None,
        raw_input=payload.get("input", ""),
        requires_native=requires_native,
    )
    return replace(request, responses=controls)


def render_responses_or_native(response: NormalizedResponse) -> dict[str, Any]:
    if response.native_responses is not None:
        return dict(response.native_responses)
    return render_responses_response(response)


def _native_sse(event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "message")
    return f"event: {event_type}\ndata: {json.dumps(event)}\n\n"


async def _prepend(
    first: StreamChunk,
    rest: AsyncIterator[StreamChunk],
) -> AsyncIterator[StreamChunk]:
    yield first
    async for chunk in rest:
        yield chunk


async def render_responses_stream_or_native(
    chunks: AsyncIterator[StreamChunk],
    model: str,
) -> AsyncIterator[str]:
    iterator = chunks.__aiter__()
    try:
        first = await anext(iterator)
    except StopAsyncIteration:
        async for event in render_responses_stream(_empty_chunks(), model):
            yield event
        return

    if first.native_responses_event is not None:
        yield _native_sse(first.native_responses_event)
        async for chunk in iterator:
            if chunk.native_responses_event is not None:
                yield _native_sse(chunk.native_responses_event)
        return

    async for event in render_responses_stream(_prepend(first, iterator), model):
        yield event


async def _empty_chunks() -> AsyncIterator[StreamChunk]:
    if False:
        yield StreamChunk(provider="", model="")
