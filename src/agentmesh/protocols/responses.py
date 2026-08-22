from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agentmesh.domain import (
    FunctionCall,
    Message,
    NormalizedRequest,
    NormalizedResponse,
    StreamChunk,
)


@dataclass(slots=True)
class _TextStreamState:
    item_id: str
    output_index: int
    chunks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _FunctionStreamState:
    item_id: str
    output_index: int
    call_id: str | None = None
    name: str | None = None
    argument_deltas: list[str] = field(default_factory=list)
    emitted_argument_count: int = 0
    announced: bool = False


def _part_text(part: object) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        kind = part.get("type")
        if kind in {"input_text", "output_text", "text"}:
            return str(part.get("text", ""))
    return ""


def _output_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (_part_text(part) for part in value)))
    if value is None:
        return ""
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _arguments_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, separators=(",", ":"), sort_keys=True)


def _input_messages(value: object) -> list[Message]:
    if isinstance(value, str):
        return [Message(role="user", content=value)]
    if not isinstance(value, list):
        return []
    messages: list[Message] = []
    for item in value:
        if isinstance(item, str):
            messages.append(Message(role="user", content=item))
            continue
        if not isinstance(item, dict):
            continue

        kind = item.get("type")
        if kind == "function_call":
            call = FunctionCall(
                call_id=str(item.get("call_id") or item.get("id") or ""),
                name=str(item.get("name") or ""),
                arguments=_arguments_text(item.get("arguments")),
            )
            messages.append(Message(role="assistant", content="", tool_calls=(call,)))
            continue
        if kind == "function_call_output":
            messages.append(
                Message(
                    role="tool",
                    content=_output_text(item.get("output")),
                    tool_call_id=str(item.get("call_id") or ""),
                )
            )
            continue

        if kind in {"message", None} or "role" in item:
            role = str(item.get("role", "user"))
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            content = item.get("content", "")
            if isinstance(content, list):
                text = "\n".join(filter(None, (_part_text(part) for part in content)))
            else:
                text = _part_text(content)
            messages.append(Message(role=role, content=text))  # type: ignore[arg-type]
    return messages


def parse_responses_request(payload: dict[str, Any]) -> NormalizedRequest:
    messages: list[Message] = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions:
        messages.append(Message(role="system", content=instructions))
    messages.extend(_input_messages(payload.get("input", "")))
    return NormalizedRequest(
        model=str(payload.get("model", "auto")),
        messages=tuple(messages),
        max_tokens=payload.get("max_output_tokens"),
        temperature=payload.get("temperature"),
        stream=bool(payload.get("stream", False)),
        tools=tuple(payload.get("tools") or ()),
        metadata=dict(payload.get("metadata") or {}),
    )


def response_envelope(
    response_id: str,
    model: str,
    *,
    status: str,
    output: list[dict[str, Any]],
    provider: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    created_at: int | None = None,
) -> dict[str, Any]:
    created = int(time.time()) if created_at is None else created_at
    usage = None
    if input_tokens is not None and output_tokens is not None:
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    body: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "status": status,
        "completed_at": int(time.time()) if status == "completed" else None,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": None,
        "model": model,
        "output": output,
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": True,
        "temperature": 1.0,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1.0,
        "truncation": "disabled",
        "usage": usage,
        "user": None,
        "metadata": {},
    }
    if provider is not None:
        body["provider"] = provider
    return body


def render_responses_response(response: NormalizedResponse) -> dict[str, Any]:
    response_id = (
        response.raw_id
        if response.raw_id and response.raw_id.startswith("resp_")
        else f"resp_{uuid.uuid4().hex}"
    )
    output: list[dict[str, Any]] = []
    for call in response.tool_calls:
        output.append(
            {
                "type": "function_call",
                "id": f"fc_{uuid.uuid4().hex}",
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
                "status": "completed",
            }
        )

    if response.content or not output:
        output.append(
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex}",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": response.content,
                        "annotations": [],
                    }
                ],
            }
        )

    return response_envelope(
        response_id,
        response.model,
        status="completed",
        output=output,
        provider=response.provider,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    event = {"type": event_type, **payload}
    return f"event: {event_type}\ndata: {json.dumps(event)}\n\n"


def _function_item(state: _FunctionStreamState, *, status: str) -> dict[str, Any]:
    return {
        "type": "function_call",
        "id": state.item_id,
        "call_id": state.call_id or "",
        "name": state.name or "",
        "arguments": "".join(state.argument_deltas),
        "status": status,
    }


async def render_responses_stream(
    chunks: AsyncIterator[StreamChunk],
    model: str,
) -> AsyncIterator[str]:
    response_id = f"resp_{uuid.uuid4().hex}"
    created_at = int(time.time())
    sequence = 0
    next_output_index = 0
    text_state: _TextStreamState | None = None
    function_states: dict[int, _FunctionStreamState] = {}
    output_order: list[tuple[str, object]] = []
    provider_name: str | None = None
    model_name = model

    in_progress = response_envelope(
        response_id,
        model,
        status="in_progress",
        output=[],
        created_at=created_at,
    )
    yield _sse(
        "response.created",
        {"response": in_progress, "sequence_number": sequence},
    )
    sequence += 1
    yield _sse(
        "response.in_progress",
        {"response": in_progress, "sequence_number": sequence},
    )
    sequence += 1

    async for chunk in chunks:
        provider_name = chunk.provider
        model_name = chunk.model
        if chunk.done:
            continue

        if chunk.text:
            if text_state is None:
                text_state = _TextStreamState(
                    item_id=f"msg_{uuid.uuid4().hex}",
                    output_index=next_output_index,
                )
                next_output_index += 1
                output_order.append(("text", text_state))
                added_item = {
                    "type": "message",
                    "id": text_state.item_id,
                    "status": "in_progress",
                    "role": "assistant",
                    "content": [],
                }
                yield _sse(
                    "response.output_item.added",
                    {
                        "output_index": text_state.output_index,
                        "item": added_item,
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                empty_part = {
                    "type": "output_text",
                    "text": "",
                    "annotations": [],
                }
                yield _sse(
                    "response.content_part.added",
                    {
                        "item_id": text_state.item_id,
                        "output_index": text_state.output_index,
                        "content_index": 0,
                        "part": empty_part,
                        "sequence_number": sequence,
                    },
                )
                sequence += 1

            text_state.chunks.append(chunk.text)
            yield _sse(
                "response.output_text.delta",
                {
                    "item_id": text_state.item_id,
                    "output_index": text_state.output_index,
                    "content_index": 0,
                    "delta": chunk.text,
                    "sequence_number": sequence,
                },
            )
            sequence += 1

        delta = chunk.function_call_delta
        if delta is not None:
            state = function_states.get(delta.index)
            if state is None:
                state = _FunctionStreamState(
                    item_id=f"fc_{uuid.uuid4().hex}",
                    output_index=next_output_index,
                )
                next_output_index += 1
                function_states[delta.index] = state
                output_order.append(("function", state))
            if delta.call_id:
                state.call_id = delta.call_id
            if delta.name:
                state.name = delta.name
            if delta.arguments_delta:
                state.argument_deltas.append(delta.arguments_delta)

            if not state.announced and state.name:
                if state.call_id is None:
                    state.call_id = f"call_{uuid.uuid4().hex}"
                added_call = _function_item(state, status="in_progress")
                added_call["arguments"] = ""
                yield _sse(
                    "response.output_item.added",
                    {
                        "output_index": state.output_index,
                        "item": added_call,
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                state.announced = True

            if state.announced:
                while state.emitted_argument_count < len(state.argument_deltas):
                    argument_delta = state.argument_deltas[state.emitted_argument_count]
                    yield _sse(
                        "response.function_call_arguments.delta",
                        {
                            "item_id": state.item_id,
                            "output_index": state.output_index,
                            "delta": argument_delta,
                            "sequence_number": sequence,
                        },
                    )
                    sequence += 1
                    state.emitted_argument_count += 1

    completed_output: list[tuple[int, dict[str, Any]]] = []
    for kind, raw_state in output_order:
        if kind == "text":
            state = raw_state
            assert isinstance(state, _TextStreamState)
            text = "".join(state.chunks)
            completed_part = {
                "type": "output_text",
                "text": text,
                "annotations": [],
            }
            completed_item = {
                "type": "message",
                "id": state.item_id,
                "status": "completed",
                "role": "assistant",
                "content": [completed_part],
            }
            yield _sse(
                "response.output_text.done",
                {
                    "item_id": state.item_id,
                    "output_index": state.output_index,
                    "content_index": 0,
                    "text": text,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
            yield _sse(
                "response.content_part.done",
                {
                    "item_id": state.item_id,
                    "output_index": state.output_index,
                    "content_index": 0,
                    "part": completed_part,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
            yield _sse(
                "response.output_item.done",
                {
                    "output_index": state.output_index,
                    "item": completed_item,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
            completed_output.append((state.output_index, completed_item))
            continue

        state = raw_state
        assert isinstance(state, _FunctionStreamState)
        if not state.name:
            raise ValueError("streamed function call ended without a function name")
        if state.call_id is None:
            state.call_id = f"call_{uuid.uuid4().hex}"
        if not state.announced:
            added_call = _function_item(state, status="in_progress")
            added_call["arguments"] = ""
            yield _sse(
                "response.output_item.added",
                {
                    "output_index": state.output_index,
                    "item": added_call,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
            state.announced = True
        while state.emitted_argument_count < len(state.argument_deltas):
            argument_delta = state.argument_deltas[state.emitted_argument_count]
            yield _sse(
                "response.function_call_arguments.delta",
                {
                    "item_id": state.item_id,
                    "output_index": state.output_index,
                    "delta": argument_delta,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
            state.emitted_argument_count += 1

        arguments = "".join(state.argument_deltas)
        yield _sse(
            "response.function_call_arguments.done",
            {
                "item_id": state.item_id,
                "output_index": state.output_index,
                "name": state.name,
                "arguments": arguments,
                "sequence_number": sequence,
            },
        )
        sequence += 1
        completed_item = _function_item(state, status="completed")
        yield _sse(
            "response.output_item.done",
            {
                "output_index": state.output_index,
                "item": completed_item,
                "sequence_number": sequence,
            },
        )
        sequence += 1
        completed_output.append((state.output_index, completed_item))

    completed_output.sort(key=lambda item: item[0])
    completed = response_envelope(
        response_id,
        model_name,
        status="completed",
        output=[item for _, item in completed_output],
        provider=provider_name,
        created_at=created_at,
    )
    yield _sse(
        "response.completed",
        {"response": completed, "sequence_number": sequence},
    )
