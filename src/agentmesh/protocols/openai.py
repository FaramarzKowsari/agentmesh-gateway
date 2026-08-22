from __future__ import annotations

import json
import time
import uuid
from typing import Any

from agentmesh.domain import FunctionCall, Message, NormalizedRequest, NormalizedResponse


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


def _arguments_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, separators=(",", ":"), sort_keys=True)


def parse_openai_request(payload: dict[str, Any]) -> NormalizedRequest:
    messages: list[Message] = []
    for item in payload.get("messages", []):
        role = str(item.get("role", "user"))
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        tool_calls = tuple(
            FunctionCall(
                call_id=str(call.get("id") or ""),
                name=str((call.get("function") or {}).get("name") or ""),
                arguments=_arguments_text(
                    (call.get("function") or {}).get("arguments")
                ),
            )
            for call in item.get("tool_calls", [])
            if isinstance(call, dict)
        )
        messages.append(
            Message(
                role=role,  # type: ignore[arg-type]
                content=_content_to_text(item.get("content", "")),
                tool_calls=tool_calls,
                tool_call_id=(
                    str(item.get("tool_call_id"))
                    if item.get("tool_call_id") is not None
                    else None
                ),
            )
        )
    return NormalizedRequest(
        model=str(payload.get("model", "auto")),
        messages=tuple(messages),
        max_tokens=payload.get("max_tokens"),
        temperature=payload.get("temperature"),
        stream=bool(payload.get("stream", False)),
        tools=tuple(payload.get("tools") or ()),
    )


def render_openai_response(response: NormalizedResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.content}
    if response.tool_calls:
        message["content"] = response.content or None
        message["tool_calls"] = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in response.tool_calls
        ]
    return {
        "id": response.raw_id or f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response.model,
        "provider": response.provider,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if response.tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": response.input_tokens or 0,
            "completion_tokens": response.output_tokens or 0,
            "total_tokens": (response.input_tokens or 0) + (response.output_tokens or 0),
        },
    }
