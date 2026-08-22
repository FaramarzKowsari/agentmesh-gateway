from agentmesh.routing.state import RuntimeStateStore


def test_success_resets_open_circuit_and_failure_streak() -> None:
    states = RuntimeStateStore(["p"])

    states.record_failure(
        "p",
        "temporary",
        threshold=1,
        cooldown_seconds=60,
    )
    failed = states.get("p")
    assert failed.failures == 1
    assert failed.consecutive_failures == 1
    assert failed.available() is False
    assert failed.last_error == "temporary"

    states.record_success("p", 25.0)
    recovered = states.get("p")

    assert recovered.successes == 1
    assert recovered.failures == 1
    assert recovered.consecutive_failures == 0
    assert recovered.available() is True
    assert recovered.last_error is None
    assert recovered.circuit_open_until == 0.0
    assert recovered.latency_ewma_ms == 25.0


def test_success_updates_latency_ewma() -> None:
    states = RuntimeStateStore(["p"])

    states.record_success("p", 100.0)
    states.record_success("p", 20.0)

    assert states.get("p").latency_ewma_ms == 80.0
