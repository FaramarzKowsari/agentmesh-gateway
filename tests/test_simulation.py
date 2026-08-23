from __future__ import annotations

import json

from typer.testing import CliRunner

from agentmesh.cli import app
from agentmesh.config import ProviderSpec
from agentmesh.quality import quality_profiles_from_dict
from agentmesh.simulation import parse_policies, render_csv, render_json, simulate


def specs() -> tuple[ProviderSpec, ...]:
    return (
        ProviderSpec(
            "cheap",
            "openai",
            "http://cheap",
            ("m",),
            cost_hint=0.1,
            quality_hint=0.6,
            input_cost_per_million=1.0,
            output_cost_per_million=2.0,
            request_quota_limit=1,
            request_quota_window_seconds=100.0,
        ),
        ProviderSpec(
            "fast",
            "openai",
            "http://fast",
            ("m",),
            cost_hint=0.8,
            quality_hint=0.9,
            input_cost_per_million=4.0,
            output_cost_per_million=8.0,
        ),
    )


def trace() -> list[dict[str, object]]:
    outcomes = {
        "cheap": {
            "success": True,
            "latency_ms": 300.0,
            "input_tokens": 100,
            "output_tokens": 50,
            "quality": 0.7,
        },
        "fast": {
            "success": True,
            "latency_ms": 80.0,
            "input_tokens": 100,
            "output_tokens": 50,
            "quality": 0.9,
        },
    }
    return [
        {"id": "r1", "at_seconds": 0.0, "model": "m", "outcomes": outcomes},
        {"id": "r2", "at_seconds": 1.0, "model": "m", "outcomes": outcomes},
    ]


def quality_profiles():
    return quality_profiles_from_dict(
        {
            "schema_version": 1,
            "benchmark_id": "fixture",
            "benchmark_version": "1",
            "source": "synthetic test fixture only",
            "metric": "fixture_score",
            "profiles": [
                {
                    "provider": "cheap",
                    "model": "m",
                    "task_class": "text",
                    "score": 0.1,
                    "sample_count": 10,
                },
                {
                    "provider": "fast",
                    "model": "m",
                    "task_class": "text",
                    "score": 0.95,
                    "sample_count": 10,
                },
            ],
        }
    )


def test_simulation_resets_state_per_policy_and_applies_quota() -> None:
    result = simulate(specs(), trace(), ("ordered", "cost"))
    ordered, cost = result["policies"]

    assert [row["provider"] for row in ordered["rows"]] == ["cheap", "fast"]
    assert [row["provider"] for row in cost["rows"]] == ["cheap", "fast"]
    assert ordered["rows"][0]["quota_pressure"] == 1.0
    assert ordered["summary"]["successes"] == 2
    assert ordered["summary"]["cost_observations"] == 2


def test_simulation_rendering_is_deterministic() -> None:
    first = simulate(specs(), trace(), ("ordered", "balanced"))
    second = simulate(specs(), trace(), ("ordered", "balanced"))
    assert render_json(first) == render_json(second)
    csv_text = render_csv(first)
    assert csv_text.startswith("policy,request_id,at_seconds,task_class,provider,status")
    assert "ordered,r1,0.0,text,cheap,success" in csv_text


def test_adaptive_balanced_uses_contextual_quality_profile() -> None:
    result = simulate(specs(), trace()[:1], ("adaptive_balanced",), quality_profiles())
    row = result["policies"][0]["rows"][0]
    assert row["provider"] == "fast"
    assert row["profile_quality"] == 0.95
    assert result["quality_profile"]["benchmark_id"] == "fixture"


def test_adaptive_policy_never_bypasses_capability_feasibility() -> None:
    providers = (
        ProviderSpec(
            "text-only",
            "openai",
            "http://text",
            ("m",),
            capabilities=("text",),
            quality_hint=1.0,
        ),
        ProviderSpec(
            "tools",
            "openai",
            "http://tools",
            ("m",),
            capabilities=("text", "tools"),
            quality_hint=0.1,
        ),
    )
    row_trace = [
        {
            "id": "tool-request",
            "model": "m",
            "requirements": ["tools"],
            "outcomes": {
                "tools": {"latency_ms": 100, "quality": 0.5},
                "text-only": {"latency_ms": 1, "quality": 1.0},
            },
        }
    ]
    result = simulate(providers, row_trace, ("adaptive_balanced", "constrained_ucb"))
    assert [policy["rows"][0]["provider"] for policy in result["policies"]] == [
        "tools",
        "tools",
    ]


def test_constrained_ucb_updates_from_chosen_feedback() -> None:
    providers = (
        ProviderSpec("a", "openai", "http://a", ("m",), cost_hint=0.0, quality_hint=0.5),
        ProviderSpec("b", "openai", "http://b", ("m",), cost_hint=0.0, quality_hint=0.5),
    )
    outcomes = {
        "a": {"latency_ms": 5000, "quality": 0.0},
        "b": {"latency_ms": 100, "quality": 1.0},
    }
    row_trace = [
        {"id": "one", "model": "m", "outcomes": outcomes},
        {"id": "two", "model": "m", "outcomes": outcomes},
    ]
    result = simulate(providers, row_trace, ("constrained_ucb",))
    policy = result["policies"][0]
    assert [row["provider"] for row in policy["rows"]] == ["a", "b"]
    assert policy["bandit"]["text:a"]["count"] == 1
    assert policy["bandit"]["text:b"]["count"] == 1


def test_parse_policies_accepts_adaptive_and_rejects_unknown_policy() -> None:
    assert parse_policies("adaptive_balanced,constrained_ucb") == (
        "adaptive_balanced",
        "constrained_ucb",
    )
    try:
        parse_policies("balanced,magic")
    except ValueError as exc:
        assert "magic" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_cli_simulate_writes_json(tmp_path) -> None:
    provider_path = tmp_path / "providers.json"
    trace_path = tmp_path / "trace.jsonl"
    profile_path = tmp_path / "quality.json"
    output_path = tmp_path / "result.json"
    provider_path.write_text(
        json.dumps(
            [
                {
                    "name": "local",
                    "adapter": "openai",
                    "base_url": "http://local",
                    "models": ["m"],
                    "input_cost_per_million": 0,
                    "output_cost_per_million": 0,
                }
            ]
        ),
        encoding="utf-8",
    )
    trace_path.write_text(
        json.dumps(
            {
                "id": "one",
                "model": "m",
                "outcomes": {
                    "local": {
                        "latency_ms": 10,
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "quality": 1.0,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": "fixture",
                "benchmark_version": "1",
                "source": "test fixture",
                "metric": "fixture_score",
                "profiles": [
                    {
                        "provider": "local",
                        "model": "m",
                        "task_class": "text",
                        "score": 1.0,
                        "sample_count": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "simulate",
            "--providers",
            str(provider_path),
            "--trace",
            str(trace_path),
            "--policies",
            "adaptive_balanced",
            "--quality-profiles",
            str(profile_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["policies"][0]["rows"][0]["provider"] == "local"
    assert payload["quality_profile"]["benchmark_id"] == "fixture"
