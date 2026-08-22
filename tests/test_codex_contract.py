from __future__ import annotations

import json
import tomllib
from pathlib import Path

import httpx
import pytest

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider

FIXTURE = Path(__file__).parent / "fixtures" / "codex" / "config.toml"


def _parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        event_type = event_line.removeprefix("event: ")
        payload = json.loads(data_line.removeprefix("data: "))
        events.append((event_type, payload))
    return events


def test_codex_config_fixture_targets_responses_without_websockets() -> None:
    config = tomllib.loads(FIXTURE.read_text(encoding="utf-8"))
    provider = config["model_providers"]["agentmesh"]

    assert config["model_provider"] == "agentmesh"
    assert provider["base_url"] == "http://127.0.0.1:8787/v1"
    assert provider["wire_api"] == "responses"
    assert provider["supports_websockets"] is False


@pytest.mark.asyncio
async def test_codex_responses_contract_round_trips_through_fake_upstream() -> None:
    captured: dict[str, object] = {}

    async def upstream_handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        payload = json.loads(request.content)
        captured["payload"] = payload

        assert request.url.path == "/v1/chat/completions"
        assert payload["model"] == "m"
        assert payload["stream"] is True
        assert payload["messages"][:2] == [
            {"role": "system", "content": "You are a coding agent."},
            {"role": "user", "content": "Reply with exactly: CONTRACT_OK"},
        ]
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["function"]["name"] == "read_file"
        assert payload["tools"][0]["function"]["parameters"]["required"] == ["path"]

        stream = "".join(
            [
                "data: {\"model\":\"m\",\"choices\":[{\"delta\":{\"content\":\"CONTRACT_\"}}]}\n\n",
                "data: {\"model\":\"m\",\"choices\":[{\"delta\":{\"content\":\"OK\"}}]}\n\n",
                "data: [DONE]\n\n",
            ]
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=stream,
        )

    settings = Settings(
        providers=(
            ProviderSpec(
                name="mock",
                adapter="openai",
                base_url="http://upstream/v1",
                models=("m",),
            ),
        )
    )
    app = create_app(settings)
    provider = app.state.registry.get("mock")
    assert isinstance(provider, OpenAICompatibleProvider)
    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    provider._client = upstream_client

    request_payload = {
        "model": "m",
        "instructions": "You are a coding agent.",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Reply with exactly: CONTRACT_OK",
                    }
                ],
            }
        ],
        "tools": [
            {
                "type": "function",
                "name": "read_file",
                "description": "Read a local file by path.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ],
        "parallel_tool_calls": False,
        "store": False,
        "stream": True,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://agentmesh",
    ) as client:
        response = await client.post("/v1/responses", json=request_payload)

    await upstream_client.aclose()

    assert response.status_code == 200
    assert captured["path"] == "/v1/chat/completions"
    events = _parse_sse(response.text)
    event_types = [event_type for event_type, _ in events]

    assert event_types == [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]
    completed = events[-1][1]["response"]
    assert isinstance(completed, dict)
    assert completed["model"] == "m"
    assert completed["provider"] == "mock"
    assert completed["output"][0]["content"][0]["text"] == "CONTRACT_OK"
