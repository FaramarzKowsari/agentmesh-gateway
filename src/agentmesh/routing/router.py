from __future__ import annotations

from agentmesh.config import ProviderSpec, RoutingPolicy
from agentmesh.domain import NormalizedRequest
from agentmesh.routing.state import RuntimeStateStore


class Router:
    def __init__(
        self,
        specs: tuple[ProviderSpec, ...],
        states: RuntimeStateStore,
        policy: RoutingPolicy = "balanced",
    ) -> None:
        self.specs = specs
        self.states = states
        self.policy = policy

    def rank(self, request: NormalizedRequest) -> list[ProviderSpec]:
        candidates = [
            spec
            for spec in self.specs
            if self.states.get(spec.name).available()
            and (request.model == "auto" or request.model in spec.models)
        ]
        if self.policy == "ordered":
            return candidates
        return sorted(candidates, key=self._score)

    def _score(self, spec: ProviderSpec) -> float:
        state = self.states.get(spec.name)
        latency = state.latency_ewma_ms if state.latency_ewma_ms is not None else 1000.0
        latency_norm = min(max(latency / 5000.0, 0.0), 1.0)
        cost = min(max(spec.cost_hint, 0.0), 1.0)
        quality_penalty = 1.0 - min(max(spec.quality_hint, 0.0), 1.0)
        weight_penalty = 1.0 / max(spec.weight, 0.01)

        if self.policy == "latency":
            return latency_norm * weight_penalty
        if self.policy == "cost":
            return cost * weight_penalty
        if self.policy == "quality":
            return quality_penalty * weight_penalty
        return (0.45 * latency_norm + 0.30 * cost + 0.25 * quality_penalty) * weight_penalty
