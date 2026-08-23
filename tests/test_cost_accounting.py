from __future__ import annotations

import json

import httpx
import pytest

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.errors import ConfigurationError
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider
from agentmesh.providers.openai_responses import OpenAIResponsesProvider


def priced_spec(
    *,
    adapter: str = "openai",
    input_price: float | None = 2.0,
    output_price: float | None = 8.0,
) -> ProviderSpec:
    return ProviderSpec(
        name="priced",
        adapter=adapter,  # type: ignore[arg-type]
        base_url="http://upstream/v1",
        models=("m",),
        input_cost_per_million=input_price,
        output_cost_per_million=output_price,
    )


def test_exact_per_million_cost_formula_and_zero_price() -> None:
    spec = priced_spec()
    free = priced_spec(input_price=0.0, output_price=0.0)

    assert spec.observed_cost_usd(1000, 500) == pytest.approx(0.006)
    assert free.observed_cost_usd(1000, 500) == 0.0


def test_missing_usage_or_price_does_not_manufacture_cost() -> None:
    missing_price = priced_spec(output_price=None)

    assert missing_price.observed_cost_usd(1000, 500) is None
    assert priced_spec().observed_cost_usd(None, 500) is None
    assert priced_spec().observed_cost_usd(1000, None) is None


def test_provider_json_rejects_negative_token_price() -> None:
    with pytest.raises(ConfigurationError, match="input_cost_per_million must be non-negative"):
        ProviderSpec.from_dict(
            {
                "name": "x",
                "adapter": "openai",
                "base_url": "http://x",
                "models": ["m"],
                "input_cost_per_million": -1,
                "output_cost_per_million": 0,
            }
        )


def test_provider_json_preserves_explicit_zero_prices() -> None:
    spec = ProviderSpec.from_dict(
        {
            "name": "x",
            "adapter": "openai",
            "base_url": "http://x",
            "models": ["m"],
            "input_cost_per_million": 0,
            "output_cost_per_million": 0.0,
        }
    )

    assert spec.input_cost_per_million == 0.0
    assert spec.output_cost_per_million == 0.0
    assert spec.observed_cost_usd(10, 20) == 0.0


@pytest.mark.asyncio
async def test_nonstream_success_records_observed_usage_and_cost() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_usage",
                "model": "m",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            },
        )

    settings = Settings(providers=(priced_spec(),))
    app = create_app(settings)
    provider = app.state.registry.get("priced")
    assert isinstance(provider, OpenAICompatibleProvider)
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider._client = upstream

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
        admin = await client.get("/admin/providers")

    await upstream.aclose()

    assert response.status_code == 200
    state = app.state.states.get("priced")
    assert state.input_tokens_total == 1000
    assert state.output_tokens_total == 500
    assert state.token_usage_observations == 1
    assert state.cost_total_usd == pytest.approx(0.006)
    assert state.cost_observations == 1
    assert state.last_cost_usd == pytest.approx(0.006)
    assert admin.json()["priced"]["cost_total_usd"] == pytest.approx(0.006)


@pytest.mark.asyncio
async def test_missing_nonstream_usage_records_no_observation() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_no_usage",
                "model": "m",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            },
        )

    app = create_app(Settings(providers=(priced_spec(),)))
    provider = app.state.registry.get("priced")
    assert isinstance(provider, OpenAICompatibleProvider)
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider._client = upstream

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )

    await upstream.aclose()

    assert response.status_code == 200
    state = app.state.states.get("priced")
    assert state.token_usage_observations == 0
    assert state.cost_observations == 0
    assert state.cost_total_usd == 0.0
    assert state.last_cost_usd is None


@pytest.mark.asyncio
async def test_failed_attempt_records_no_usage_or_cost() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "temporary"}})

    app = create_app(Settings(providers=(priced_spec(),)))
    provider = app.state.registry.get("priced")
    assert isinstance(provider, OpenAICompatibleProvider)
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider._client = upstream

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )

    await upstream.aclose()

    assert response.status_code == 502
    state = app.state.states.get("priced")
    assert state.successes == 0
    assert state.failures == 1
    assert state.token_usage_observations == 0
    assert state.cost_observations == 0


@pytest.mark.asyncio
async def test_native_responses_stream_records_exact_completed_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/responses"
        events = [
            {
                "type": "response.created",
                "response": {"id": "resp_usage", "model": "m", "status": "in_progress"},
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_usage",
                    "object": "response",
                    "model": "m",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "id": "msg_1",
                            "status": "completed",
                            "role": "assistant",
                            "content": [
                                {"type": "output_text", "text": "ok", "annotations": []}
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 2000, "output_tokens": 1000},
                },
            },
        ]
        body = "".join(
            f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
        )

    spec = ProviderSpec(
        name="native",
        adapter="responses",
        base_url="http://upstream/v1",
        models=("m",),
        input_cost_per_million=1.5,
        output_cost_per_million=3.0,
    )
    app = create_app(Settings(providers=(spec,)))
    provider = app.state.registry.get("native")
    assert isinstance(provider, OpenAIResponsesProvider)
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider._client = upstream

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://agentmesh") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "m", "input": "hi", "stream": True},
        )

    await upstream.aclose()

    assert response.status_code == 200
    state = app.state.states.get("native")
    assert state.input_tokens_total == 2000
    assert state.output_tokens_total == 1000
    assert state.token_usage_observations == 1
    assert state.cost_total_usd == pytest.approx(0.006)
    assert state.cost_observations == 1
