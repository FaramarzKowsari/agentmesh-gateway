from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from agentmesh.app import create_app
from agentmesh.config import Settings
from agentmesh.domain import (
    CanonicalRequest,
    CanonicalResponse,
    ProviderFailure,
    ProviderMetadata,
    normalize_error,
)
from agentmesh.resilience import CircuitBreaker, CircuitState
from agentmesh.routing import Router
from agentmesh.schemas import ChatRequest, MessagesRequest, ResponsesRequest


@dataclass
class FakeProvider:
    name: str
    metadata: ProviderMetadata
    fails: bool = False
    calls: int = 0

    async def complete(self, request: CanonicalRequest) -> CanonicalResponse:
        self.calls += 1
        if self.fails:
            raise ProviderFailure("secret upstream detail")
        return CanonicalResponse(id="result-1", model=request.model, text=f"from {self.name}", provider=self.name)

    async def health(self) -> bool:
        return True

    async def stream(self, request: CanonicalRequest):
        yield "text"


def provider(name="first", priority=1, **kwargs):
    return FakeProvider(name, ProviderMetadata(priority=priority, models=("model-a",), **kwargs))


def client(providers=None, settings=None):
    router = Router([provider()] if providers is None else providers, max_attempts=1)
    return TestClient(create_app(settings or Settings(), router))


def test_health_and_readiness():
    with client() as api:
        assert api.get("/health").json() == {"status": "ok"}
        assert api.get("/ready").status_code == 200
    with client([]) as api:
        assert api.get("/ready").status_code == 503


def test_protocol_parsing():
    assert ChatRequest(model="x", messages=[{"role": "user", "content": "hi"}]).canonical().messages[0].content == "hi"
    assert ResponsesRequest(model="x", input="hello").canonical().messages[0].role == "user"
    assert MessagesRequest(model="x", max_tokens=5, messages=[{"role": "user", "content": "hello"}]).canonical().max_tokens == 5


@pytest.mark.asyncio
async def test_ordered_and_auto_selection():
    late, early = provider("late", 9), provider("early", 1)
    result = await Router([late, early], max_attempts=1).execute(CanonicalRequest(model="auto", messages=[]))
    assert result.provider == "early"
    assert result.model == "model-a"


@pytest.mark.asyncio
async def test_balanced_routing_rotates():
    a, b = provider("a"), provider("b")
    router = Router([a, b], "balanced", max_attempts=1)
    request = CanonicalRequest(model="model-a", messages=[])
    assert (await router.execute(request)).provider == "a"
    assert (await router.execute(request)).provider == "b"


@pytest.mark.asyncio
async def test_fallback_and_retry():
    broken, healthy = provider("broken", fails=True), provider("healthy", priority=2)
    result = await Router([broken, healthy], max_attempts=2).execute(CanonicalRequest(model="model-a", messages=[]))
    assert result.provider == "healthy"
    assert broken.calls == 2


def test_circuit_breaker():
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=100)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not breaker.allow_request()
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


def test_authentication_and_model_catalog():
    settings = Settings(bearer_token="local-test-token")
    with client(settings=settings) as api:
        assert api.get("/v1/models").status_code == 401
        response = api.get("/v1/models", headers={"Authorization": "Bearer local-test-token"})
        assert response.json()["data"][0]["id"] == "model-a"


def test_chat_responses_anthropic_and_streaming():
    with client() as api:
        chat = api.post("/v1/chat/completions", json={"model": "model-a", "messages": [{"role": "user", "content": "hi"}]})
        assert chat.json()["choices"][0]["message"]["content"] == "from first"
        response = api.post("/v1/responses", json={"model": "model-a", "input": "hi", "stream": True})
        assert "response.output_text.delta" in response.text
        message = api.post("/v1/messages", json={"model": "model-a", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]})
        assert message.json()["content"][0]["text"] == "from first"


def test_error_normalization_does_not_leak_detail():
    error = normalize_error(ProviderFailure("api-key=very-secret"))
    assert error.status == 503
    assert "secret" not in error.message
