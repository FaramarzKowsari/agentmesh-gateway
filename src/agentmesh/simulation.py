from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from agentmesh.config import ProviderSpec, RoutingPolicy
from agentmesh.domain import Message, NormalizedRequest, ReasoningControls, ResponsesControls
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore

BASELINE_POLICIES: tuple[RoutingPolicy, ...] = (
    "ordered",
    "latency",
    "cost",
    "quality",
    "balanced",
)
REQUIREMENTS = frozenset({"text", "tools", "reasoning", "native_responses_tools"})


@dataclass(slots=True)
class SimulationClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value

    def set(self, value: float) -> None:
        if value < self.value:
            raise ValueError("trace at_seconds must be non-decreasing")
        self.value = value


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


def parse_policies(value: str) -> tuple[RoutingPolicy, ...]:
    names = tuple(part.strip() for part in value.split(",") if part.strip())
    if not names:
        raise ValueError("at least one policy is required")
    unknown = [name for name in names if name not in BASELINE_POLICIES]
    if unknown:
        raise ValueError(f"unsupported simulation policies: {', '.join(unknown)}")
    return tuple(cast(RoutingPolicy, name) for name in names)


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


def simulate_policy(
    specs: tuple[ProviderSpec, ...],
    trace: list[dict[str, Any]],
    policy: RoutingPolicy,
) -> dict[str, Any]:
    clock = SimulationClock()
    states = RuntimeStateStore([spec.name for spec in specs], clock=clock)
    router = Router(specs, states, policy)
    spec_by_name = {spec.name: spec for spec in specs}
    rows: list[dict[str, Any]] = []

    for index, item in enumerate(trace):
        at_seconds = _nonnegative_float(item.get("at_seconds", index), "at_seconds")
        clock.set(at_seconds)
        request = request_from_trace(item)
        ranked = router.rank(request)
        request_id = str(item.get("id", f"request-{index + 1}"))
        if not ranked:
            rows.append(
                {
                    "request_id": request_id,
                    "at_seconds": at_seconds,
                    "provider": None,
                    "status": "no_provider",
                    "latency_ms": None,
                    "cost_usd": None,
                    "quality": None,
                    "quota_pressure": None,
                }
            )
            continue

        spec = ranked[0]
        states.record_attempt(spec.name)
        outcomes = item.get("outcomes")
        if not isinstance(outcomes, dict) or not isinstance(outcomes.get(spec.name), dict):
            rows.append(
                {
                    "request_id": request_id,
                    "at_seconds": at_seconds,
                    "provider": spec.name,
                    "status": "missing_outcome",
                    "latency_ms": None,
                    "cost_usd": None,
                    "quality": None,
                    "quota_pressure": states.quota_snapshot(spec.name)["pressure"],
                }
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
            rows.append(
                {
                    "request_id": request_id,
                    "at_seconds": at_seconds,
                    "provider": spec.name,
                    "status": "provider_failure",
                    "latency_ms": None,
                    "cost_usd": None,
                    "quality": None,
                    "quota_pressure": states.quota_snapshot(spec.name)["pressure"],
                }
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
        rows.append(
            {
                "request_id": request_id,
                "at_seconds": at_seconds,
                "provider": spec.name,
                "status": "success",
                "latency_ms": latency_ms,
                "cost_usd": cost_usd,
                "quality": quality,
                "quota_pressure": states.quota_snapshot(spec.name)["pressure"],
            }
        )

    return {"policy": policy, "summary": _summary(rows), "rows": rows}


def simulate(
    specs: tuple[ProviderSpec, ...],
    trace: list[dict[str, Any]],
    policies: tuple[RoutingPolicy, ...] = BASELINE_POLICIES,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policies": [simulate_policy(specs, trace, policy) for policy in policies],
    }


def render_json(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def render_csv(result: dict[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "policy",
        "request_id",
        "at_seconds",
        "provider",
        "status",
        "latency_ms",
        "cost_usd",
        "quality",
        "quota_pressure",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for policy_result in result["policies"]:
        for row in policy_result["rows"]:
            writer.writerow({"policy": policy_result["policy"], **row})
    return buffer.getvalue()
