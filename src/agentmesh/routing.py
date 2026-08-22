"""Provider selection and resilient execution."""

import asyncio
from collections import defaultdict

from .domain import CanonicalRequest, CanonicalResponse, GatewayError, Provider
from .resilience import CircuitBreaker


class Router:
    def __init__(self, providers: list[Provider], strategy: str = "ordered", *, failure_threshold: int = 3, recovery_seconds: float = 30, max_attempts: int = 2):
        self.providers, self.strategy, self.max_attempts = providers, strategy, max_attempts
        self.breakers = {p.name: CircuitBreaker(failure_threshold, recovery_seconds) for p in providers}
        self._uses: dict[str, int] = defaultdict(int)

    def candidates(self, model: str) -> list[Provider]:
        eligible = [p for p in self.providers if (model == "auto" or not p.metadata.models or model in p.metadata.models) and self.breakers[p.name].allow_request()]
        keys = {
            "ordered": lambda p: p.metadata.priority,
            "balanced": lambda p: (self._uses[p.name], p.metadata.priority),
            "cost": lambda p: (p.metadata.cost, p.metadata.priority),
            "latency": lambda p: (p.metadata.latency, p.metadata.priority),
            "quality": lambda p: (-p.metadata.quality, p.metadata.priority),
        }
        return sorted(eligible, key=keys[self.strategy])

    async def execute(self, request: CanonicalRequest) -> CanonicalResponse:
        failures = 0
        for provider in self.candidates(request.model):
            selected_model = request.model if request.model != "auto" else (provider.metadata.models[0] if provider.metadata.models else "auto")
            routed = request.model_copy(update={"model": selected_model})
            for attempt in range(self.max_attempts):
                try:
                    result = await provider.complete(routed)
                    self.breakers[provider.name].record_success()
                    self._uses[provider.name] += 1
                    return result
                except Exception:
                    failures += 1
                    if attempt + 1 < self.max_attempts:
                        await asyncio.sleep(0)
            self.breakers[provider.name].record_failure()
        raise GatewayError("All eligible providers failed", code="providers_unavailable", status=503) from None
