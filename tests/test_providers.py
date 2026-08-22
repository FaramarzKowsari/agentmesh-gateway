from __future__ import annotations

import json

import httpx
import pytest

from agentmesh.config import ProviderSpec
from agentmesh.domain import Message, NormalizedRequest
from agentmesh.errors import ProviderError
from agentmesh.providers.anthropic import AnthropicProvider
from agentmesh.providers.openai_compatible import OpenAICompatibleProvider


def request(model: str = "m") -> NormalizedRequest:
    return NormalizedRequest(
        model=model,
        messages=(
            Message("system", "be precise"),
            Message("user", "hello"),
        ),
        max_tokens=64,
        temperature=0.2,
    )


@pytest.mark.asyncio
async def test_openai_provider_normalizes_response_and_usage() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/chat/completions"
        payload = json.loads(req.content)
        assert payload["model"] == "m"
        assert payload["messages"][1]["content"] == "hello"
        assert payload["max_tokens"] == 64
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "m",
                "choices": [{"message": {"content": "answer"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://provider",
    )
    spec = ProviderSpec("p", "openai", "http://provider/v1", ("m",))
    provider = OpenAICompatibleProvider(spec, client)

    response = await provider.complete(request())

    assert response.provider == "p"
    assert response.content == "answer"
    assert response.input_tokens == 3
    assert response.output_tokens == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_provider_429_is_retryable_and_body_is_not_leaked() -> None:
    async def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="secret vendor diagnostic: sk-do-not-leak")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        ProviderSpec("p", "openai", "http://provider/v1", ("m",)),
        client,
    )

    with pytest.raises(ProviderError) as caught:
        await provider.complete(request())

    assert caught.value.retryable is True
    assert caught.value.status_code == 429
    assert "sk-do-not-leak" not in str(caught.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_anthropic_provider_maps_system_message_and_usage() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/messages"
        payload = json.loads(req.content)
        assert payload["system"] == "be precise"
        assert payload["messages"] == [{"role": "user", "content": "hello"}]
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "model": "m",
                "content": [{"type": "text", "text": "answer"}],
                "usage": {"input_tokens": 4, "output_tokens": 2},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://provider",
    )
    provider = AnthropicProvider(
        ProviderSpec("a", "anthropic", "http://provider", ("m",)),
        client,
    )

    response = await provider.complete(request())

    assert response.provider == "a"
    assert response.content == "answer"
    assert response.input_tokens == 4
    assert response.output_tokens == 2
    await client.aclose()
