from __future__ import annotations

from typing import Any

from agentmesh.errors import ClientRequestError

SUPPORTED_ITEM_TYPES = {"message", "function_call", "function_call_output"}
SUPPORTED_MESSAGE_PART_TYPES = {"input_text", "output_text", "text"}


def _unsupported(feature: str, description: str) -> ClientRequestError:
    return ClientRequestError(
        description,
        code="unsupported_feature",
        feature=feature,
    )


def _validate_message_content(content: object) -> None:
    if isinstance(content, str):
        return
    if not isinstance(content, list):
        raise ClientRequestError("Responses message content must be a string or a list")
    for part in content:
        if isinstance(part, str):
            continue
        if not isinstance(part, dict):
            raise ClientRequestError("Responses message content parts must be objects or strings")
        part_type = part.get("type")
        if part_type not in SUPPORTED_MESSAGE_PART_TYPES:
            feature = f"responses.content.{part_type or 'unknown'}"
            raise _unsupported(
                feature,
                f"Responses content part type '{part_type}' is not supported by AgentMesh",
            )


def _validate_input_item(item: object) -> None:
    if isinstance(item, str):
        return
    if not isinstance(item, dict):
        raise ClientRequestError("Responses input items must be strings or objects")

    item_type = item.get("type")
    if item_type is None and "role" in item:
        item_type = "message"
    if item_type not in SUPPORTED_ITEM_TYPES:
        feature = f"responses.input.{item_type or 'unknown'}"
        raise _unsupported(
            feature,
            f"Responses input item type '{item_type}' is not supported by AgentMesh",
        )

    if item_type == "message":
        if "role" not in item:
            raise ClientRequestError("Responses message input requires a role")
        _validate_message_content(item.get("content", ""))
        return

    if item_type == "function_call":
        if not item.get("call_id") and not item.get("id"):
            raise ClientRequestError("Responses function_call requires call_id or id")
        if not item.get("name"):
            raise ClientRequestError("Responses function_call requires a function name")
        return

    if not item.get("call_id"):
        raise ClientRequestError("Responses function_call_output requires call_id")


def _validate_tools(tools: object) -> None:
    if tools is None:
        return
    if not isinstance(tools, list):
        raise ClientRequestError("Responses tools must be a list")
    for tool in tools:
        if not isinstance(tool, dict):
            raise ClientRequestError("Responses tool definitions must be objects")
        tool_type = tool.get("type")
        if tool_type != "function":
            feature = f"responses.tool.{tool_type or 'unknown'}"
            raise _unsupported(
                feature,
                f"Responses tool type '{tool_type}' is not supported by AgentMesh",
            )
        if not tool.get("name") and not isinstance(tool.get("function"), dict):
            raise ClientRequestError("Responses function tools require a function name")


def validate_responses_payload(payload: dict[str, Any]) -> None:
    input_value = payload.get("input", "")
    if isinstance(input_value, str):
        pass
    elif isinstance(input_value, list):
        for item in input_value:
            _validate_input_item(item)
    else:
        raise ClientRequestError("Responses input must be a string or a list")

    _validate_tools(payload.get("tools"))
