from __future__ import annotations

import json
import uuid
from typing import Any

from agentmesh.domain import FunctionCall, Message, NormalizedRequest, NormalizedResponse


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


def _tool_result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _extract_text(content)
    if content is None:
        return ""
    return json.dumps(content, separators=(",", ":"), sort_keys=True)


def _arguments_object(arguments: str) -> object:
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return {"raw": arguments}


def parse_anthropic_request(payload: dict[str, Any]) -> NormalizedRequest:
    messages: list[Message] = []
    system = payload.get("system")
    if system:
        messages.append(Message(role="system", content=_extract_text(system)))
    for item in payload.get("messages", []):
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = item.get("content")
        if not isinstance(content, list):
            messages.append(Message(role=role, content=_extract_text(content)))
            continue

        text = _extract_text(content)
        tool_calls = tuple(
            FunctionCall(
                call_id=str(block.get("id") or ""),
                name=str(block.get("name") or ""),
                arguments=json.dumps(
                    block.get("input") or {},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        )
        if role == "assistant":
            messages.append(Message(role="assistant", content=text, tool_calls=tool_calls))
            continue

        if text:
            messages.append(Message(role="user", content=text))
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            messages.append(
                Message(
                    role="tool",
                    content=_tool_result_text(block.get("content")),
                    tool_call_id=str(block.get("tool_use_id") or ""),
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


def render_anthropic_response(response: NormalizedResponse) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if response.content:
        content.append({"type": "text", "text": response.content})
    content.extend(
        {
            "type": "tool_use",
            "id": call.call_id,
            "name": call.name,
            "input": _arguments_object(call.arguments),
        }
        for call in response.tool_calls
    )
    return {
        "id": response.raw_id or f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": response.model,
        "provider": response.provider,
        "content": content,
        "stop_reason": "tool_use" if response.tool_calls else "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": response.input_tokens or 0,
            "output_tokens": response.output_tokens or 0,
        },
    }
