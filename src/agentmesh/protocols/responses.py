from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from agentmesh.domain import Message, NormalizedRequest, NormalizedResponse, StreamChunk


def _part_text(part: object) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        kind = part.get("type")
        if kind in {"input_text", "output_text", "text"}:
            return str(part.get("text", ""))
    return ""


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
        if item.get("type") in {"message", None} or "role" in item:
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
    item_id = f"msg_{uuid.uuid4().hex}"
    output = [
        {
            "type": "message",
            "id": item_id,
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
    ]
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


async def render_responses_stream(
    chunks: AsyncIterator[StreamChunk],
    model: str,
) -> AsyncIterator[str]:
    response_id = f"resp_{uuid.uuid4().hex}"
    item_id = f"msg_{uuid.uuid4().hex}"
    created_at = int(time.time())
    sequence = 0

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

    added_item = {
        "type": "message",
        "id": item_id,
        "status": "in_progress",
        "role": "assistant",
        "content": [],
    }
    yield _sse(
        "response.output_item.added",
        {
            "output_index": 0,
            "item": added_item,
            "sequence_number": sequence,
        },
    )
    sequence += 1

    empty_part = {"type": "output_text", "text": "", "annotations": []}
    yield _sse(
        "response.content_part.added",
        {
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": empty_part,
            "sequence_number": sequence,
        },
    )
    sequence += 1

    accumulated: list[str] = []
    provider_name: str | None = None
    model_name = model
    async for chunk in chunks:
        provider_name = chunk.provider
        model_name = chunk.model
        if chunk.done:
            continue
        accumulated.append(chunk.text)
        yield _sse(
            "response.output_text.delta",
            {
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "delta": chunk.text,
                "sequence_number": sequence,
            },
        )
        sequence += 1

    text = "".join(accumulated)
    completed_part = {"type": "output_text", "text": text, "annotations": []}
    completed_item = {
        "type": "message",
        "id": item_id,
        "status": "completed",
        "role": "assistant",
        "content": [completed_part],
    }

    yield _sse(
        "response.output_text.done",
        {
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "text": text,
            "sequence_number": sequence,
        },
    )
    sequence += 1
    yield _sse(
        "response.content_part.done",
        {
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": completed_part,
            "sequence_number": sequence,
        },
    )
    sequence += 1
    yield _sse(
        "response.output_item.done",
        {
            "output_index": 0,
            "item": completed_item,
            "sequence_number": sequence,
        },
    )
    sequence += 1

    completed = response_envelope(
        response_id,
        model_name,
        status="completed",
        output=[completed_item],
        provider=provider_name,
        created_at=created_at,
    )
    yield _sse(
        "response.completed",
        {"response": completed, "sequence_number": sequence},
    )
