from __future__ import annotations

import time
from collections.abc import AsyncIterator

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

    async def complete(self, request: NormalizedRequest) -> NormalizedResponse:
        candidates = self.router.rank(request)
        if not candidates:
            raise NoProviderAvailable("no provider is currently eligible for this request")

        last_error: ProviderError | None = None
        for spec in candidates[: self.max_attempts]:
            provider = self.registry.get(spec.name)
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
            started = time.perf_counter()
            committed = False
            try:
                async for chunk in provider.stream(request):
                    committed = True
                    yield chunk
                latency_ms = (time.perf_counter() - started) * 1000
                self.states.record_success(spec.name, latency_ms)
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
