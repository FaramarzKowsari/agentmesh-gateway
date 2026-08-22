from agentmesh.domain import FunctionCall, NormalizedResponse
from agentmesh.protocols.anthropic import (
    parse_anthropic_request,
    render_anthropic_response,
)
from agentmesh.protocols.openai import parse_openai_request, render_openai_response


def test_parse_openai_request() -> None:
    req = parse_openai_request(
        {"model": "auto", "messages": [{"role": "user", "content": "hello"}]}
    )
    assert req.model == "auto"
    assert req.messages[0].content == "hello"


def test_parse_openai_tool_call_and_result() -> None:
    req = parse_openai_request(
        {
            "model": "m",
            "messages": [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": "{\"q\":\"x\"}",
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": "result",
                },
            ],
        }
    )

    assistant = req.messages[0]
    assert assistant.role == "assistant"
    assert assistant.tool_calls[0] == FunctionCall(
        call_id="call_1",
        name="lookup",
        arguments="{\"q\":\"x\"}",
    )
    assert req.messages[1].role == "tool"
    assert req.messages[1].tool_call_id == "call_1"
    assert req.messages[1].content == "result"


def test_parse_anthropic_system() -> None:
    req = parse_anthropic_request(
        {
            "model": "auto",
            "system": "be precise",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "hi"}]}
            ],
        }
    )
    assert req.messages[0].role == "system"
    assert req.messages[1].content == "hi"


def test_parse_anthropic_tool_use_and_result() -> None:
    req = parse_anthropic_request(
        {
            "model": "m",
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "lookup",
                            "input": {"q": "x"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "result",
                        }
                    ],
                },
            ],
        }
    )

    assistant = req.messages[0]
    assert assistant.tool_calls[0] == FunctionCall(
        call_id="call_1",
        name="lookup",
        arguments="{\"q\":\"x\"}",
    )
    assert req.messages[1].role == "tool"
    assert req.messages[1].tool_call_id == "call_1"
    assert req.messages[1].content == "result"


def test_render_openai_response() -> None:
    response = NormalizedResponse(provider="p", model="m", content="ok")
    wire = render_openai_response(response)
    assert wire["choices"][0]["message"]["content"] == "ok"
    assert wire["provider"] == "p"


def test_render_openai_tool_call_response() -> None:
    response = NormalizedResponse(
        provider="p",
        model="m",
        content="",
        tool_calls=(
            FunctionCall(
                call_id="call_1",
                name="lookup",
                arguments="{\"q\":\"x\"}",
            ),
        ),
    )
    wire = render_openai_response(response)
    choice = wire["choices"][0]

    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] is None
    assert choice["message"]["tool_calls"][0]["id"] == "call_1"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "lookup"


def test_render_anthropic_response() -> None:
    response = NormalizedResponse(provider="p", model="m", content="ok")
    wire = render_anthropic_response(response)
    assert wire["content"][0]["text"] == "ok"


def test_render_anthropic_tool_use_response() -> None:
    response = NormalizedResponse(
        provider="p",
        model="m",
        content="",
        tool_calls=(
            FunctionCall(
                call_id="call_1",
                name="lookup",
                arguments="{\"q\":\"x\"}",
            ),
        ),
    )
    wire = render_anthropic_response(response)

    assert wire["stop_reason"] == "tool_use"
    assert wire["content"] == [
        {
            "type": "tool_use",
            "id": "call_1",
            "name": "lookup",
            "input": {"q": "x"},
        }
    ]
