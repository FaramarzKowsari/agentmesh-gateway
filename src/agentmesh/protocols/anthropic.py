from __future__ import annotations

import uuid
from typing import Any

from agentmesh.domain import Message, NormalizedRequest, NormalizedResponse


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def parse_anthropic_request(payload: dict[str, Any]) -> NormalizedRequest:
    messages: list[Message] = []
    system = payload.get("system")
    if system:
        messages.append(Message(role="system", content=_extract_text(system)))
    for item in payload.get("messages", []):
        role = "assistant" if item.get("role") == "assistant" else "user"
        messages.append(Message(role=role, content=_extract_text(item.get("content"))))
    return NormalizedRequest(
        model=str(payload.get("model", "auto")),
        messages=tuple(messages),
        max_tokens=payload.get("max_tokens"),
        temperature=payload.get("temperature"),
        stream=bool(payload.get("stream", False)),
        tools=tuple(payload.get("tools") or ()),
    )


def render_anthropic_response(response: NormalizedResponse) -> dict[str, Any]:
    return {
        "id": response.raw_id or f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": response.model,
        "provider": response.provider,
        "content": [{"type": "text", "text": response.content}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": response.input_tokens or 0,
            "output_tokens": response.output_tokens or 0,
        },
    }
