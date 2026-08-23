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
    input_tokens_total: int = 0
    output_tokens_total: int = 0
    token_usage_observations: int = 0
    cost_total_usd: float = 0.0
    cost_observations: int = 0
    last_input_tokens: int | None = None
    last_output_tokens: int | None = None
    last_cost_usd: float | None = None

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

    def record_usage(
        self,
        name: str,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        valid_input = input_tokens if input_tokens is not None and input_tokens >= 0 else None
        valid_output = output_tokens if output_tokens is not None and output_tokens >= 0 else None
        if valid_input is None and valid_output is None:
            return

        state = self._states[name]
        state.token_usage_observations += 1
        state.last_input_tokens = valid_input
        state.last_output_tokens = valid_output
        if valid_input is not None:
            state.input_tokens_total += valid_input
        if valid_output is not None:
            state.output_tokens_total += valid_output

        if cost_usd is not None and cost_usd >= 0:
            state.cost_total_usd += cost_usd
            state.cost_observations += 1
            state.last_cost_usd = cost_usd
        else:
            state.last_cost_usd = None

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
