from fastapi.testclient import TestClient

from agentmesh.api.app import create_app
from agentmesh.config import ProviderSpec, Settings
from agentmesh.routing.state import DEFAULT_LATENCY_SAMPLE_WINDOW, RuntimeStateStore


def test_latency_distribution_is_empty_before_successes() -> None:
    state = RuntimeStateStore(["p"]).get("p")

    assert state.latency_sample_count == 0
    assert state.latency_window_size == DEFAULT_LATENCY_SAMPLE_WINDOW
    assert state.latency_p50_ms is None
    assert state.latency_p95_ms is None


def test_single_success_sets_ewma_p50_and_p95() -> None:
    states = RuntimeStateStore(["p"])

    states.record_success("p", 12.5)
    state = states.get("p")

    assert state.latency_ewma_ms == 12.5
    assert state.latency_sample_count == 1
    assert state.latency_p50_ms == 12.5
    assert state.latency_p95_ms == 12.5


def test_nearest_rank_percentiles_are_deterministic() -> None:
    states = RuntimeStateStore(["p"])
    for latency in (10.0, 20.0, 30.0, 40.0, 100.0):
        states.record_success("p", latency)

    state = states.get("p")

    assert state.latency_sample_count == 5
    assert state.latency_p50_ms == 30.0
    assert state.latency_p95_ms == 100.0


def test_latency_window_evicts_oldest_success() -> None:
    states = RuntimeStateStore(["p"], latency_sample_window=3)
    for latency in (10.0, 20.0, 30.0, 100.0):
        states.record_success("p", latency)

    state = states.get("p")

    assert state.latency_window_size == 3
    assert state.latency_sample_count == 3
    assert list(state.latency_samples_ms) == [20.0, 30.0, 100.0]
    assert state.latency_p50_ms == 30.0
    assert state.latency_p95_ms == 100.0


def test_failure_does_not_enter_latency_distribution() -> None:
    states = RuntimeStateStore(["p"], latency_sample_window=2)
    states.record_success("p", 50.0)
    states.record_failure("p", "temporary", threshold=3, cooldown_seconds=30.0)

    state = states.get("p")

    assert state.successes == 1
    assert state.failures == 1
    assert state.latency_sample_count == 1
    assert state.latency_p50_ms == 50.0


def test_existing_ewma_formula_is_unchanged() -> None:
    states = RuntimeStateStore(["p"])
    states.record_success("p", 100.0)
    states.record_success("p", 200.0)

    assert states.get("p").latency_ewma_ms == 125.0


def test_latency_sample_window_must_be_positive() -> None:
    try:
        RuntimeStateStore(["p"], latency_sample_window=0)
    except ValueError as exc:
        assert str(exc) == "latency_sample_window must be at least 1"
    else:
        raise AssertionError("zero latency window must be rejected")


def test_admin_provider_state_exposes_latency_distribution() -> None:
    settings = Settings(
        providers=(ProviderSpec("p", "openai", "http://local", ("m",)),),
    )
    app = create_app(settings)
    app.state.states.record_success("p", 10.0)
    app.state.states.record_success("p", 30.0)
    client = TestClient(app)

    response = client.get("/admin/providers")

    assert response.status_code == 200
    provider = response.json()["p"]
    assert provider["latency_sample_count"] == 2
    assert provider["latency_window_size"] == DEFAULT_LATENCY_SAMPLE_WINDOW
    assert provider["latency_p50_ms"] == 10.0
    assert provider["latency_p95_ms"] == 30.0
