from __future__ import annotations

import pytest

from agentmesh.domain import Message, NormalizedRequest, ReasoningControls, ResponsesControls
from agentmesh.quality import classify_task, quality_profiles_from_dict


def profile_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "benchmark_id": "bench",
        "benchmark_version": "1",
        "source": "reproducible fixture procedure",
        "metric": "pass_rate",
        "profiles": [
            {
                "provider": "p",
                "model": "m",
                "task_class": "text",
                "score": 0.8,
                "sample_count": 20,
            }
        ],
    }


def test_quality_profiles_require_provenance() -> None:
    data = profile_document()
    del data["source"]
    with pytest.raises(ValueError, match="source"):
        quality_profiles_from_dict(data)


def test_quality_profiles_reject_duplicates_and_bad_scores() -> None:
    data = profile_document()
    profiles = data["profiles"]
    assert isinstance(profiles, list)
    profiles.append(dict(profiles[0]))
    with pytest.raises(ValueError, match="unique"):
        quality_profiles_from_dict(data)

    data = profile_document()
    profiles = data["profiles"]
    assert isinstance(profiles, list)
    entry = profiles[0]
    assert isinstance(entry, dict)
    entry["score"] = 1.2
    with pytest.raises(ValueError, match="between 0 and 1"):
        quality_profiles_from_dict(data)


def test_quality_profile_lookup_is_contextual() -> None:
    profiles = quality_profiles_from_dict(profile_document())
    assert profiles.score_for("p", "m", "text") == 0.8
    assert profiles.sample_count_for("p", "m", "text") == 20
    assert profiles.score_for("p", "m", "tool") is None


def test_task_classification_uses_request_semantics() -> None:
    text = NormalizedRequest("m", (Message("user", "hello"),))
    tool = NormalizedRequest(
        "m",
        (Message("user", "hello"),),
        tools=({"type": "function", "name": "x", "parameters": {}},),
    )
    reasoning = NormalizedRequest(
        "m",
        (Message("user", "hello"),),
        responses=ResponsesControls(reasoning=ReasoningControls(effort="medium")),
    )
    native_tool = NormalizedRequest(
        "m",
        (Message("user", "hello"),),
        tools=({"type": "web_search"},),
        responses=ResponsesControls(requires_native=True),
    )

    assert classify_task(text) == "text"
    assert classify_task(tool) == "tool"
    assert classify_task(reasoning) == "reasoning"
    assert classify_task(native_tool) == "native_tool"
