from __future__ import annotations

import time
import uuid
from typing import Any

from agentmesh.domain import Message, NormalizedRequest, NormalizedResponse


def _content_to_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and item.get("type") in {"text", "input_text"}:
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(value or "")


def parse_openai_request(payload: dict[str, Any]) -> NormalizedRequest:
    messages: list[Message] = []
    for item in payload.get("messages", []):
        role = str(item.get("role", "user"))
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        messages.append(Message(role=role, content=_content_to_text(item.get("content", ""))))  # type: ignore[arg-type]
    return NormalizedRequest(
        model=str(payload.get("model", "auto")),
        messages=tuple(messages),
        max_tokens=payload.get("max_tokens"),
        temperature=payload.get("temperature"),
        stream=bool(payload.get("stream", False)),
        tools=tuple(payload.get("tools") or ()),
    )


def render_openai_response(response: NormalizedResponse) -> dict[str, Any]:
    return {
        "id": response.raw_id or f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response.model,
        "provider": response.provider,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response.content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": response.input_tokens or 0,
            "completion_tokens": response.output_tokens or 0,
            "total_tokens": (response.input_tokens or 0) + (response.output_tokens or 0),
        },
    }
