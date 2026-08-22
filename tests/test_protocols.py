from agentmesh.domain import NormalizedResponse
from agentmesh.protocols.anthropic import parse_anthropic_request, render_anthropic_response
from agentmesh.protocols.openai import parse_openai_request, render_openai_response


def test_parse_openai_request() -> None:
    req = parse_openai_request(
        {"model": "auto", "messages": [{"role": "user", "content": "hello"}]}
    )
    assert req.model == "auto"
    assert req.messages[0].content == "hello"


def test_parse_anthropic_system() -> None:
    req = parse_anthropic_request(
        {
            "model": "auto",
            "system": "be precise",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        }
    )
    assert req.messages[0].role == "system"
    assert req.messages[1].content == "hi"


def test_render_openai_response() -> None:
    response = NormalizedResponse(provider="p", model="m", content="ok")
    wire = render_openai_response(response)
    assert wire["choices"][0]["message"]["content"] == "ok"
    assert wire["provider"] == "p"


def test_render_anthropic_response() -> None:
    response = NormalizedResponse(provider="p", model="m", content="ok")
    wire = render_anthropic_response(response)
    assert wire["content"][0]["text"] == "ok"
