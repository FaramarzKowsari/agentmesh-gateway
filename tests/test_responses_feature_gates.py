from __future__ import annotations

import httpx
import pytest

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider


def app_with_forbidden_upstream() -> tuple[object, httpx.AsyncClient]:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError(f"upstream must not be called; calls={calls}")

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
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider._client = upstream
    return app, upstream


async def post(payload: dict[str, object]) -> httpx.Response:
    app, upstream = app_with_forbidden_upstream()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post("/v1/responses", json=payload)
    await upstream.aclose()
    return response


@pytest.mark.asyncio
async def test_reasoning_input_requires_native_responses_provider() -> None:
    response = await post(
        {
            "model": "m",
            "input": [{"type": "reasoning", "summary": []}],
        }
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {"message": "no provider is currently eligible for this request"}
    }


@pytest.mark.asyncio
async def test_native_only_stream_is_rejected_before_stream_headers_start() -> None:
    response = await post(
        {
            "model": "m",
            "input": "continue",
            "reasoning": {"effort": "high"},
            "stream": True,
        }
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["message"] == (
        "no provider is currently eligible for this request"
    )


@pytest.mark.asyncio
async def test_rejects_unsupported_image_content_part() -> None:
    response = await post(
        {
            "model": "m",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": "https://example.invalid/image.png",
                        }
                    ],
                }
            ],
        }
    )

    assert response.status_code == 400
    assert response.json()["error"]["feature"] == "responses.content.input_image"


@pytest.mark.asyncio
async def test_rejects_unsupported_builtin_tool() -> None:
    response = await post(
        {
            "model": "m",
            "input": "search the web",
            "tools": [{"type": "web_search_preview"}],
        }
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "unsupported_feature"
    assert error["feature"] == "responses.tool.web_search_preview"


@pytest.mark.asyncio
async def test_invalid_function_call_shape_is_a_client_error() -> None:
    response = await post(
        {
            "model": "m",
            "input": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "arguments": "{}",
                }
            ],
        }
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["message"] == "Responses function_call requires a function name"
