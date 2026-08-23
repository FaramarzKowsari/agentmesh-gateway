from fastapi.testclient import TestClient

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.domain import (
    Message,
    NormalizedRequest,
    ReasoningControls,
    ResponsesControls,
)
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore


def router_for(*specs: ProviderSpec, policy: str = "ordered") -> Router:
    states = RuntimeStateStore([spec.name for spec in specs])
    return Router(specs, states, policy)  # type: ignore[arg-type]


def test_plain_text_preserves_legacy_provider_defaults() -> None:
    spec = ProviderSpec("legacy", "openai", "http://legacy", ("m",))
    request = NormalizedRequest("m", (Message("user", "hello"),))

    ranked = router_for(spec).rank(request)

    assert [item.name for item in ranked] == ["legacy"]
    assert Router.required_capabilities(request) == frozenset({"text"})


def test_custom_tool_requirement_excludes_cheaper_provider_without_tools() -> None:
    text_only = ProviderSpec(
        "text-only",
        "openai",
        "http://text",
        ("m",),
        cost_hint=0.0,
        capabilities=("text",),
    )
    tool_provider = ProviderSpec(
        "tools",
        "openai",
        "http://tools",
        ("m",),
        cost_hint=1.0,
        capabilities=("text", "tools"),
    )
    request = NormalizedRequest(
        "m",
        (Message("user", "call the tool"),),
        tools=({"type": "function", "name": "lookup"},),
    )

    ranked = router_for(text_only, tool_provider, policy="cost").rank(request)

    assert Router.required_capabilities(request) == frozenset({"text", "tools"})
    assert [item.name for item in ranked] == ["tools"]


def test_reasoning_request_requires_declared_reasoning_capability() -> None:
    no_reasoning = ProviderSpec(
        "plain-responses",
        "responses",
        "http://plain",
        ("m",),
        capabilities=("text", "tools"),
    )
    reasoning = ProviderSpec(
        "reasoning-responses",
        "responses",
        "http://reasoning",
        ("m",),
        capabilities=("text", "tools", "reasoning"),
    )
    request = NormalizedRequest(
        "m",
        (Message("user", "think carefully"),),
        responses=ResponsesControls(
            reasoning=ReasoningControls(effort="high"),
            requires_native=True,
        ),
    )

    ranked = router_for(no_reasoning, reasoning).rank(request)

    assert Router.required_capabilities(request) == frozenset({"text", "reasoning"})
    assert [item.name for item in ranked] == ["reasoning-responses"]


def test_native_tool_request_requires_native_tool_capability() -> None:
    reasoning_only = ProviderSpec(
        "reasoning-only",
        "responses",
        "http://reasoning",
        ("m",),
        capabilities=("text", "tools", "reasoning"),
    )
    native_tools = ProviderSpec(
        "native-tools",
        "responses",
        "http://native",
        ("m",),
        capabilities=("text", "tools", "native_responses_tools"),
    )
    request = NormalizedRequest(
        "m",
        (Message("user", "search"),),
        tools=({"type": "web_search_preview"},),
        responses=ResponsesControls(requires_native=True),
    )

    ranked = router_for(reasoning_only, native_tools).rank(request)

    assert Router.required_capabilities(request) == frozenset(
        {"text", "tools", "native_responses_tools"}
    )
    assert [item.name for item in ranked] == ["native-tools"]


def test_reasoning_include_requires_reasoning_capability() -> None:
    request = NormalizedRequest(
        "m",
        (Message("user", "continue"),),
        responses=ResponsesControls(
            include=("reasoning.encrypted_content",),
            requires_native=True,
        ),
    )

    assert Router.required_capabilities(request) == frozenset({"text", "reasoning"})


def test_admin_provider_state_exposes_effective_capabilities() -> None:
    settings = Settings(
        providers=(
            ProviderSpec(
                "restricted",
                "openai",
                "http://local",
                ("m",),
                capabilities=("text",),
            ),
        )
    )
    client = TestClient(create_app(settings))

    response = client.get("/admin/providers")

    assert response.status_code == 200
    assert response.json()["restricted"]["capabilities"] == ["text"]
