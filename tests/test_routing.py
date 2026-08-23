from agentmesh.config import ProviderSpec
from agentmesh.domain import (
    Message,
    NormalizedRequest,
    ReasoningControls,
    ResponsesControls,
)
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore


def specs() -> tuple[ProviderSpec, ...]:
    return (
        ProviderSpec("cheap", "openai", "http://cheap", ("m",), cost_hint=0.1, quality_hint=0.5),
        ProviderSpec(
            "quality",
            "openai",
            "http://quality",
            ("m",),
            cost_hint=0.8,
            quality_hint=0.95,
        ),
    )


def request() -> NormalizedRequest:
    return NormalizedRequest("m", (Message("user", "hi"),))


def test_cost_policy_prefers_cheaper_provider() -> None:
    items = specs()
    states = RuntimeStateStore([x.name for x in items])
    router = Router(items, states, "cost")
    assert router.rank(request())[0].name == "cheap"


def test_quality_policy_prefers_higher_quality_provider() -> None:
    items = specs()
    states = RuntimeStateStore([x.name for x in items])
    router = Router(items, states, "quality")
    assert router.rank(request())[0].name == "quality"


def test_open_circuit_is_excluded() -> None:
    items = specs()
    states = RuntimeStateStore([x.name for x in items])
    states.record_failure("cheap", "x", threshold=1, cooldown_seconds=60)
    router = Router(items, states, "cost")
    assert [x.name for x in router.rank(request())] == ["quality"]


def test_reasoning_semantics_route_only_to_native_responses_provider() -> None:
    items = (
        ProviderSpec("chat", "openai", "http://chat", ("m",)),
        ProviderSpec("native", "responses", "http://native", ("m",)),
    )
    states = RuntimeStateStore([x.name for x in items])
    router = Router(items, states, "ordered")
    native_request = NormalizedRequest(
        "m",
        (Message("user", "hi"),),
        responses=ResponsesControls(
            reasoning=ReasoningControls(effort="high", summary="auto"),
            raw_input="hi",
            requires_native=True,
        ),
    )

    assert [x.name for x in router.rank(native_request)] == ["native"]


def test_non_responses_ingress_does_not_route_to_native_adapter() -> None:
    items = (
        ProviderSpec("native", "responses", "http://native", ("m",)),
        ProviderSpec("chat", "openai", "http://chat", ("m",)),
    )
    states = RuntimeStateStore([x.name for x in items])
    router = Router(items, states, "ordered")

    assert [x.name for x in router.rank(request())] == ["chat"]
