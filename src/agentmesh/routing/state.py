from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class ProviderRuntimeState:
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    latency_ewma_ms: float | None = None
    circuit_open_until: float = 0.0
    last_error: str | None = None

    def available(self, now: float | None = None) -> bool:
        return self.circuit_open_until <= (time.monotonic() if now is None else now)


class RuntimeStateStore:
    def __init__(self, provider_names: list[str]) -> None:
        self._states = {name: ProviderRuntimeState() for name in provider_names}

    def get(self, name: str) -> ProviderRuntimeState:
        return self._states[name]

    def snapshot(self) -> dict[str, ProviderRuntimeState]:
        return self._states.copy()

    def record_success(self, name: str, latency_ms: float) -> None:
        state = self._states[name]
        state.successes += 1
        state.consecutive_failures = 0
        state.last_error = None
        state.circuit_open_until = 0.0
        alpha = 0.25
        state.latency_ewma_ms = (
            latency_ms
            if state.latency_ewma_ms is None
            else alpha * latency_ms + (1 - alpha) * state.latency_ewma_ms
        )

    def record_failure(
        self,
        name: str,
        error: str,
        *,
        threshold: int,
        cooldown_seconds: float,
    ) -> None:
        state = self._states[name]
        state.failures += 1
        state.consecutive_failures += 1
        state.last_error = error
        if state.consecutive_failures >= threshold:
            state.circuit_open_until = time.monotonic() + cooldown_seconds
