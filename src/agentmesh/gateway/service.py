from __future__ import annotations

import time
from collections.abc import AsyncIterator

from agentmesh.config import ProviderSpec
from agentmesh.domain import NormalizedRequest, NormalizedResponse, StreamChunk
from agentmesh.errors import NoProviderAvailable, ProviderError
from agentmesh.providers.registry import ProviderRegistry
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore


class GatewayService:
    def __init__(
        self,
        registry: ProviderRegistry,
        router: Router,
        states: RuntimeStateStore,
        *,
        max_attempts: int,
        failure_threshold: int,
        cooldown_seconds: float,
    ) -> None:
        self.registry = registry
        self.router = router
        self.states = states
        self.max_attempts = max_attempts
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

    def ensure_eligible(self, request: NormalizedRequest) -> None:
        if not self.router.rank(request):
            raise NoProviderAvailable("no provider is currently eligible for this request")

    def _record_usage(
        self,
        spec: ProviderSpec,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        self.states.record_usage(
            spec.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=spec.observed_cost_usd(input_tokens, output_tokens),
        )

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
        candidates = self.router.rank(request)
        if not candidates:
            raise NoProviderAvailable("no provider is currently eligible for this request")

        last_error: ProviderError | None = None
        for spec in candidates[: self.max_attempts]:
            provider = self.registry.get(spec.name)
            self.states.record_attempt(spec.name)
            started = time.perf_counter()
            try:
                response = await provider.complete(request)
            except ProviderError as exc:
                last_error = exc
                self.states.record_failure(
                    spec.name,
                    str(exc),
                    threshold=self.failure_threshold,
                    cooldown_seconds=self.cooldown_seconds,
                )
                if not exc.retryable:
                    raise
                continue
            latency_ms = (time.perf_counter() - started) * 1000
            self.states.record_success(spec.name, latency_ms)
            self._record_usage(spec, response.input_tokens, response.output_tokens)
            return response

        if last_error is not None:
            raise last_error
        raise NoProviderAvailable("all eligible providers were exhausted")

    async def stream(self, request: NormalizedRequest) -> AsyncIterator[StreamChunk]:
        candidates = self.router.rank(request)
        if not candidates:
            raise NoProviderAvailable("no provider is currently eligible for this request")

        last_error: ProviderError | None = None
        for spec in candidates[: self.max_attempts]:
            provider = self.registry.get(spec.name)
            self.states.record_attempt(spec.name)
            started = time.perf_counter()
            committed = False
            observed_input_tokens: int | None = None
            observed_output_tokens: int | None = None
            try:
                async for chunk in provider.stream(request):
                    if chunk.input_tokens is not None:
                        observed_input_tokens = chunk.input_tokens
                    if chunk.output_tokens is not None:
                        observed_output_tokens = chunk.output_tokens
                    if (
                        chunk.text
                        or chunk.done
                        or chunk.function_call_delta is not None
                        or chunk.native_responses_event is not None
                    ):
                        committed = True
                    yield chunk
                latency_ms = (time.perf_counter() - started) * 1000
                self.states.record_success(spec.name, latency_ms)
                self._record_usage(spec, observed_input_tokens, observed_output_tokens)
                return
            except ProviderError as exc:
                last_error = exc
                self.states.record_failure(
                    spec.name,
                    str(exc),
                    threshold=self.failure_threshold,
                    cooldown_seconds=self.cooldown_seconds,
                )
                if committed or not exc.retryable:
                    raise
                continue

        if last_error is not None:
            raise last_error
        raise NoProviderAvailable("all eligible providers were exhausted")
