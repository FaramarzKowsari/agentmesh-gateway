from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

DEFAULT_LATENCY_SAMPLE_WINDOW = 128


def _valid_token_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nearest_rank_percentile(samples: deque[float], percentile: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


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
    latency_window_size: int = DEFAULT_LATENCY_SAMPLE_WINDOW
    latency_samples_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_LATENCY_SAMPLE_WINDOW), repr=False
    )
    quota_limit: int | None = None
    quota_window_seconds: float | None = None
    quota_window_started_at: float | None = None
    quota_attempts: int = 0

    @property
    def latency_sample_count(self) -> int:
        return len(self.latency_samples_ms)

    @property
    def latency_p50_ms(self) -> float | None:
        return _nearest_rank_percentile(self.latency_samples_ms, 0.50)

    @property
    def latency_p95_ms(self) -> float | None:
        return _nearest_rank_percentile(self.latency_samples_ms, 0.95)

    def available(self, now: float | None = None) -> bool:
        return self.circuit_open_until <= (time.monotonic() if now is None else now)


class RuntimeStateStore:
    def __init__(
        self,
        provider_names: list[str],
        *,
        latency_sample_window: int = DEFAULT_LATENCY_SAMPLE_WINDOW,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if latency_sample_window < 1:
            raise ValueError("latency_sample_window must be at least 1")
        self._clock = clock
        self._states = {
            name: ProviderRuntimeState(
                latency_window_size=latency_sample_window,
                latency_samples_ms=deque(maxlen=latency_sample_window),
            )
            for name in provider_names
        }

    def get(self, name: str) -> ProviderRuntimeState:
        return self._states[name]

    def snapshot(self) -> dict[str, ProviderRuntimeState]:
        return self._states.copy()

    def configure_quota(self, name: str, limit: int | None, window_seconds: float | None) -> None:
        state = self._states[name]
        state.quota_limit = limit
        state.quota_window_seconds = window_seconds
        state.quota_window_started_at = None
        state.quota_attempts = 0

    def _refresh_quota(self, state: ProviderRuntimeState) -> None:
        if state.quota_limit is None or state.quota_window_seconds is None:
            return
        now = self._clock()
        if state.quota_window_started_at is None:
            return
        if now - state.quota_window_started_at >= state.quota_window_seconds:
            state.quota_window_started_at = None
            state.quota_attempts = 0

    def record_attempt(self, name: str) -> None:
        state = self._states[name]
        self._refresh_quota(state)
        if state.quota_limit is None or state.quota_window_seconds is None:
            return
        if state.quota_window_started_at is None:
            state.quota_window_started_at = self._clock()
        state.quota_attempts += 1

    def quota_exhausted(self, name: str) -> bool:
        state = self._states[name]
        self._refresh_quota(state)
        return state.quota_limit is not None and state.quota_attempts >= state.quota_limit

    def quota_snapshot(self, name: str) -> dict[str, object]:
        state = self._states[name]
        self._refresh_quota(state)
        if state.quota_limit is None or state.quota_window_seconds is None:
            return {
                "configured": False,
                "limit": None,
                "window_seconds": None,
                "used": 0,
                "remaining": None,
                "pressure": None,
                "exhausted": False,
                "resets_in_seconds": None,
            }
        remaining = max(state.quota_limit - state.quota_attempts, 0)
        resets_in = None
        if state.quota_window_started_at is not None:
            elapsed = self._clock() - state.quota_window_started_at
            resets_in = max(state.quota_window_seconds - elapsed, 0.0)
        return {
            "configured": True,
            "limit": state.quota_limit,
            "window_seconds": state.quota_window_seconds,
            "used": state.quota_attempts,
            "remaining": remaining,
            "pressure": state.quota_attempts / state.quota_limit,
            "exhausted": state.quota_attempts >= state.quota_limit,
            "resets_in_seconds": resets_in,
        }

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
        if math.isfinite(latency_ms) and latency_ms >= 0:
            state.latency_samples_ms.append(float(latency_ms))

    def record_usage(
        self,
        name: str,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        valid_input = _valid_token_count(input_tokens)
        valid_output = _valid_token_count(output_tokens)
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
        if isinstance(cost_usd, (int, float)) and not isinstance(cost_usd, bool) and cost_usd >= 0:
            state.cost_total_usd += float(cost_usd)
            state.cost_observations += 1
            state.last_cost_usd = float(cost_usd)
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
