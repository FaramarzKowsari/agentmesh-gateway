from agentmesh.domain import NormalizedResponse
from agentmesh.protocols.responses import parse_responses_request, render_responses_response


def test_parse_responses_string_input() -> None:
    request = parse_responses_request(
        {"model": "auto", "instructions": "be brief", "input": "hello"}
    )
    assert request.messages[0].role == "system"
    assert request.messages[1].content == "hello"


def test_parse_responses_item_input() -> None:
    request = parse_responses_request(
        {
            "model": "m",
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                }
            ],
        }
    )
    assert request.messages[0].content == "hello"


def test_render_responses_response() -> None:
    body = render_responses_response(
        NormalizedResponse(provider="p", model="m", content="answer", input_tokens=2, output_tokens=3)
    )
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output"][0]["content"][0]["text"] == "answer"
    assert body["usage"]["total_tokens"] == 5
