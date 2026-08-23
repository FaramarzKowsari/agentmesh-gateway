from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from agentmesh.config import ProviderSpec, RoutingPolicy
from agentmesh.domain import Message, NormalizedRequest, ReasoningControls, ResponsesControls
from agentmesh.quality import QualityProfiles, TaskClass, classify_task
from agentmesh.routing.router import Router
from agentmesh.routing.state import ProviderRuntimeState, RuntimeStateStore

SimulationPolicy = Literal[
    "ordered",
    "latency",
    "cost",
    "quality",
    "balanced",
    "adaptive_balanced",
    "constrained_ucb",
]
STATIC_POLICIES = frozenset({"ordered", "latency", "cost", "quality", "balanced"})
SIMULATION_POLICIES: tuple[SimulationPolicy, ...] = (
    "ordered",
    "latency",
    "cost",
    "quality",
    "balanced",
    "adaptive_balanced",
    "constrained_ucb",
)
BASELINE_POLICIES: tuple[SimulationPolicy, ...] = SIMULATION_POLICIES[:5]
REQUIREMENTS = frozenset({"text", "tools", "reasoning", "native_responses_tools"})
ADAPTIVE_COST_SCALE_USD = 0.01
UCB_EXPLORATION = 0.15


@dataclass(slots=True)
class SimulationClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value

    def set(self, value: float) -> None:
        if value < self.value:
            raise ValueError("trace at_seconds must be non-decreasing")
        self.value = value


@dataclass(slots=True)
class BanditStat:
    count: int = 0
    mean_reward: float = 0.0

    def update(self, reward: float) -> None:
        self.count += 1
        self.mean_reward += (reward - self.mean_reward) / self.count


def load_provider_specs(path: Path) -> tuple[ProviderSpec, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("providers")
    if not isinstance(data, list) or not data:
        raise ValueError("provider config must contain a non-empty provider list")
    specs = tuple(ProviderSpec.from_dict(item) for item in data if isinstance(item, dict))
    if len(specs) != len(data):
        raise ValueError("every provider entry must be an object")
    if len({spec.name for spec in specs}) != len(specs):
        raise ValueError("provider names must be unique")
    return specs


def load_trace(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"trace line {line_number} must be a JSON object")
        rows.append(value)
    if not rows:
        raise ValueError("trace must contain at least one request")
    return rows


def parse_policies(value: str) -> tuple[SimulationPolicy, ...]:
    names = tuple(part.strip() for part in value.split(",") if part.strip())
    if not names:
        raise ValueError("at least one policy is required")
    unknown = [name for name in names if name not in SIMULATION_POLICIES]
    if unknown:
        raise ValueError(f"unsupported simulation policies: {', '.join(unknown)}")
    return tuple(cast(SimulationPolicy, name) for name in names)


def request_from_trace(row: dict[str, Any]) -> NormalizedRequest:
    raw_requirements = row.get("requirements", ["text"])
    if not isinstance(raw_requirements, list) or not all(
        isinstance(item, str) for item in raw_requirements
    ):
        raise ValueError("trace requirements must be a list of strings")
    requirements = set(raw_requirements)
    unknown = requirements - REQUIREMENTS
    if unknown:
        raise ValueError(f"unsupported trace requirements: {', '.join(sorted(unknown))}")
    requirements.add("text")

    tools: tuple[dict[str, Any], ...] = ()
    controls: ResponsesControls | None = None
    if "native_responses_tools" in requirements:
        tools = ({"type": "web_search"},)
        controls = ResponsesControls(requires_native=True)
    elif "tools" in requirements:
        tools = (
            {
                "type": "function",
                "name": "simulation_tool",
                "parameters": {"type": "object", "properties": {}},
            },
        )

    if "reasoning" in requirements:
        controls = ResponsesControls(
            reasoning=ReasoningControls(effort="medium"),
            requires_native=True,
        )

    return NormalizedRequest(
        model=str(row.get("model", "auto")),
        messages=(Message("user", str(row.get("prompt", "simulation request"))),),
        tools=tools,
        responses=controls,
    )


def _nonnegative_float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    parsed = float(value)
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _optional_quality(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("quality must be numeric")
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise ValueError("quality must be between 0 and 1")
    return parsed


def _optional_tokens(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _resolved_model(spec: ProviderSpec, request: NormalizedRequest) -> str:
    if request.model != "auto" and request.model in spec.models:
        return request.model
    return spec.models[0]


def _profile_quality(
    profiles: QualityProfiles | None,
    spec: ProviderSpec,
    request: NormalizedRequest,
    task_class: TaskClass,
) -> float | None:
    if profiles is None:
        return None
    return profiles.score_for(spec.name, _resolved_model(spec, request), task_class)


def _quality_prior(
    profiles: QualityProfiles | None,
    spec: ProviderSpec,
    request: NormalizedRequest,
    task_class: TaskClass,
) -> float:
    profile = _profile_quality(profiles, spec, request, task_class)
    return _clamp(profile if profile is not None else spec.quality_hint)


def _latency_norm(state: ProviderRuntimeState) -> float:
    latency = state.latency_ewma_ms if state.latency_ewma_ms is not None else 1000.0
    return _clamp(latency / 5000.0)


def _cost_norm(spec: ProviderSpec, state: ProviderRuntimeState) -> float:
    if state.cost_observations:
        average_cost = state.cost_total_usd / state.cost_observations
        return _clamp(average_cost / ADAPTIVE_COST_SCALE_USD)
    return _clamp(spec.cost_hint)


def _quota_pressure(states: RuntimeStateStore, provider: str) -> float:
    pressure = states.quota_snapshot(provider)["pressure"]
    return _clamp(float(pressure)) if pressure is not None else 0.0


def _adaptive_penalty(
    spec: ProviderSpec,
    request: NormalizedRequest,
    task_class: TaskClass,
    states: RuntimeStateStore,
    profiles: QualityProfiles | None,
) -> float:
    state = states.get(spec.name)
    quality_penalty = 1.0 - _quality_prior(profiles, spec, request, task_class)
    return (
        0.40 * _latency_norm(state)
        + 0.25 * _cost_norm(spec, state)
        + 0.25 * quality_penalty
        + 0.10 * _quota_pressure(states, spec.name)
    )


def _outcome_reward(
    *,
    spec: ProviderSpec,
    request: NormalizedRequest,
    task_class: TaskClass,
    states: RuntimeStateStore,
    profiles: QualityProfiles | None,
    latency_ms: float | None,
    cost_usd: float | None,
    quality: float | None,
    success: bool,
) -> float:
    if not success:
        return 0.0
    quality_value = (
        quality
        if quality is not None
        else _quality_prior(profiles, spec, request, task_class)
    )
    latency_value = _clamp((latency_ms if latency_ms is not None else 1000.0) / 5000.0)
    cost_value = (
        _clamp(cost_usd / ADAPTIVE_COST_SCALE_USD)
        if cost_usd is not None
        else _cost_norm(spec, states.get(spec.name))
    )
    penalty = (
        0.40 * latency_value
        + 0.25 * cost_value
        + 0.25 * (1.0 - _clamp(quality_value))
        + 0.10 * _quota_pressure(states, spec.name)
    )
    return 1.0 - penalty


def _select_adaptive(
    candidates: list[ProviderSpec],
    *,
    policy: SimulationPolicy,
    request: NormalizedRequest,
    task_class: TaskClass,
    states: RuntimeStateStore,
    profiles: QualityProfiles | None,
    bandit: dict[tuple[TaskClass, str], BanditStat],
) -> tuple[ProviderSpec, float]:
    if policy == "adaptive_balanced":
        scored = [
            (
                _adaptive_penalty(spec, request, task_class, states, profiles),
                index,
                spec,
            )
            for index, spec in enumerate(candidates)
        ]
        penalty, _, selected = min(scored, key=lambda item: (item[0], item[1]))
        return selected, penalty

    total = sum(bandit.get((task_class, spec.name), BanditStat()).count for spec in candidates)
    scored_ucb: list[tuple[float, int, ProviderSpec]] = []
    for index, spec in enumerate(candidates):
        stat = bandit.get((task_class, spec.name), BanditStat())
        prior_reward = 1.0 - _adaptive_penalty(spec, request, task_class, states, profiles)
        estimate = stat.mean_reward if stat.count else prior_reward
        bonus = UCB_EXPLORATION * math.sqrt(math.log(total + 2.0) / (stat.count + 1.0))
        scored_ucb.append((estimate + bonus, index, spec))
    utility, _, selected = max(scored_ucb, key=lambda item: (item[0], -item[1]))
    return selected, utility


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [row for row in rows if row["status"] == "success"]
    known_costs = [float(row["cost_usd"]) for row in successes if row["cost_usd"] is not None]
    known_quality = [float(row["quality"]) for row in successes if row["quality"] is not None]
    latencies = [float(row["latency_ms"]) for row in successes]
    return {
        "requests": len(rows),
        "successes": len(successes),
        "provider_failures": sum(row["status"] == "provider_failure" for row in rows),
        "no_provider": sum(row["status"] == "no_provider" for row in rows),
        "missing_outcome": sum(row["status"] == "missing_outcome" for row in rows),
        "mean_latency_ms": sum(latencies) / len(latencies) if latencies else None,
        "observed_cost_usd": sum(known_costs),
        "cost_observations": len(known_costs),
        "mean_quality": sum(known_quality) / len(known_quality) if known_quality else None,
        "quality_observations": len(known_quality),
    }


def _empty_row(
    *,
    request_id: str,
    at_seconds: float,
    task_class: TaskClass,
    provider: str | None,
    status: str,
    profile_quality: float | None,
    selection_value: float | None,
    quota_pressure: object = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "at_seconds": at_seconds,
        "task_class": task_class,
        "provider": provider,
        "status": status,
        "latency_ms": None,
        "cost_usd": None,
        "quality": None,
        "profile_quality": profile_quality,
        "selection_value": selection_value,
        "quota_pressure": quota_pressure,
    }


def simulate_policy(
    specs: tuple[ProviderSpec, ...],
    trace: list[dict[str, Any]],
    policy: SimulationPolicy,
    profiles: QualityProfiles | None = None,
) -> dict[str, Any]:
    clock = SimulationClock()
    states = RuntimeStateStore([spec.name for spec in specs], clock=clock)
    router_policy = cast(RoutingPolicy, policy) if policy in STATIC_POLICIES else "ordered"
    router = Router(specs, states, router_policy)
    bandit: dict[tuple[TaskClass, str], BanditStat] = {}
    rows: list[dict[str, Any]] = []

    for index, item in enumerate(trace):
        at_seconds = _nonnegative_float(item.get("at_seconds", index), "at_seconds")
        clock.set(at_seconds)
        request = request_from_trace(item)
        task_class = classify_task(request)
        ranked = router.rank(request)
        request_id = str(item.get("id", f"request-{index + 1}"))
        if not ranked:
            rows.append(
                _empty_row(
                    request_id=request_id,
                    at_seconds=at_seconds,
                    task_class=task_class,
                    provider=None,
                    status="no_provider",
                    profile_quality=None,
                    selection_value=None,
                )
            )
            continue

        selection_value: float | None = None
        if policy in {"adaptive_balanced", "constrained_ucb"}:
            spec, selection_value = _select_adaptive(
                ranked,
                policy=policy,
                request=request,
                task_class=task_class,
                states=states,
                profiles=profiles,
                bandit=bandit,
            )
        else:
            spec = ranked[0]

        profile_quality = _profile_quality(profiles, spec, request, task_class)
        states.record_attempt(spec.name)
        outcomes = item.get("outcomes")
        quota_pressure = states.quota_snapshot(spec.name)["pressure"]
        if not isinstance(outcomes, dict) or not isinstance(outcomes.get(spec.name), dict):
            rows.append(
                _empty_row(
                    request_id=request_id,
                    at_seconds=at_seconds,
                    task_class=task_class,
                    provider=spec.name,
                    status="missing_outcome",
                    profile_quality=profile_quality,
                    selection_value=selection_value,
                    quota_pressure=quota_pressure,
                )
            )
            continue

        outcome = cast(dict[str, Any], outcomes[spec.name])
        success = outcome.get("success", True)
        if not isinstance(success, bool):
            raise ValueError("outcome success must be boolean")
        if not success:
            states.record_failure(
                spec.name,
                "simulated provider failure",
                threshold=1_000_000_000,
                cooldown_seconds=0,
            )
            if policy == "constrained_ucb":
                bandit.setdefault((task_class, spec.name), BanditStat()).update(0.0)
            rows.append(
                _empty_row(
                    request_id=request_id,
                    at_seconds=at_seconds,
                    task_class=task_class,
                    provider=spec.name,
                    status="provider_failure",
                    profile_quality=profile_quality,
                    selection_value=selection_value,
                    quota_pressure=quota_pressure,
                )
            )
            continue

        latency_ms = _nonnegative_float(outcome.get("latency_ms"), "latency_ms")
        input_tokens = _optional_tokens(outcome.get("input_tokens"), "input_tokens")
        output_tokens = _optional_tokens(outcome.get("output_tokens"), "output_tokens")
        quality = _optional_quality(outcome.get("quality"))
        cost_usd = spec.observed_cost_usd(input_tokens, output_tokens)
        states.record_success(spec.name, latency_ms)
        states.record_usage(
            spec.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        if policy == "constrained_ucb":
            reward = _outcome_reward(
                spec=spec,
                request=request,
                task_class=task_class,
                states=states,
                profiles=profiles,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                quality=quality,
                success=True,
            )
            bandit.setdefault((task_class, spec.name), BanditStat()).update(reward)
        rows.append(
            {
                "request_id": request_id,
                "at_seconds": at_seconds,
                "task_class": task_class,
                "provider": spec.name,
                "status": "success",
                "latency_ms": latency_ms,
                "cost_usd": cost_usd,
                "quality": quality,
                "profile_quality": profile_quality,
                "selection_value": selection_value,
                "quota_pressure": states.quota_snapshot(spec.name)["pressure"],
            }
        )

    result: dict[str, Any] = {"policy": policy, "summary": _summary(rows), "rows": rows}
    if policy == "constrained_ucb":
        result["bandit"] = {
            f"{task}:{provider}": {"count": stat.count, "mean_reward": stat.mean_reward}
            for (task, provider), stat in sorted(bandit.items())
        }
    return result


def simulate(
    specs: tuple[ProviderSpec, ...],
    trace: list[dict[str, Any]],
    policies: tuple[SimulationPolicy, ...] = BASELINE_POLICIES,
    profiles: QualityProfiles | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 2,
        "policies": [simulate_policy(specs, trace, policy, profiles) for policy in policies],
    }
    if profiles is not None:
        result["quality_profile"] = {
            "benchmark_id": profiles.benchmark_id,
            "benchmark_version": profiles.benchmark_version,
            "source": profiles.source,
            "metric": profiles.metric,
        }
    return result


def render_json(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def render_csv(result: dict[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "policy",
        "request_id",
        "at_seconds",
        "task_class",
        "provider",
        "status",
        "latency_ms",
        "cost_usd",
        "quality",
        "profile_quality",
        "selection_value",
        "quota_pressure",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for policy_result in result["policies"]:
        for row in policy_result["rows"]:
            writer.writerow({"policy": policy_result["policy"], **row})
    return buffer.getvalue()
