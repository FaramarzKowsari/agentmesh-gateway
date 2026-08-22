from __future__ import annotations

import time
import uuid
from typing import Any

from agentmesh.domain import Message, NormalizedRequest, NormalizedResponse


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
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "model": model,
        "output": output,
        "parallel_tool_calls": True,
        "tools": [],
        "metadata": {},
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
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
        input_tokens=response.input_tokens or 0,
        output_tokens=response.output_tokens or 0,
    )
