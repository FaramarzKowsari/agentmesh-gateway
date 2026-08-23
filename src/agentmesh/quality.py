from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agentmesh.domain import NormalizedRequest

TaskClass = Literal["text", "tool", "reasoning", "native_tool"]
TASK_CLASSES = frozenset({"text", "tool", "reasoning", "native_tool"})


def classify_task(request: NormalizedRequest) -> TaskClass:
    controls = request.responses
    if controls is not None:
        if any(
            isinstance(tool, dict) and tool.get("type") not in {None, "function"}
            for tool in request.tools
        ):
            return "native_tool"
        if controls.reasoning is not None or any(
            isinstance(item, dict) and item.get("type") == "reasoning"
            for item in (controls.raw_input if isinstance(controls.raw_input, list) else [])
        ):
            return "reasoning"
    if request.tools or any(
        message.tool_calls or message.tool_call_id is not None for message in request.messages
    ):
        return "tool"
    return "text"


@dataclass(slots=True, frozen=True)
class QualityProfileEntry:
    provider: str
    model: str
    task_class: TaskClass
    score: float
    sample_count: int


@dataclass(slots=True, frozen=True)
class QualityProfiles:
    benchmark_id: str
    benchmark_version: str
    source: str
    metric: str
    entries: tuple[QualityProfileEntry, ...]

    def score_for(self, provider: str, model: str, task_class: TaskClass) -> float | None:
        for entry in self.entries:
            if (
                entry.provider == provider
                and entry.model == model
                and entry.task_class == task_class
            ):
                return entry.score
        return None

    def sample_count_for(self, provider: str, model: str, task_class: TaskClass) -> int | None:
        for entry in self.entries:
            if (
                entry.provider == provider
                and entry.model == model
                and entry.task_class == task_class
            ):
                return entry.sample_count
        return None


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"quality profile {key} must be a non-empty string")
    return value.strip()


def _entry(value: object, index: int) -> QualityProfileEntry:
    if not isinstance(value, dict):
        raise ValueError(f"quality profile entry {index} must be an object")
    provider = _required_text(value, "provider")
    model = _required_text(value, "model")
    task_value = _required_text(value, "task_class")
    if task_value not in TASK_CLASSES:
        raise ValueError(f"unsupported task_class: {task_value}")
    raw_score = value.get("score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise ValueError("quality profile score must be numeric")
    score = float(raw_score)
    if not 0.0 <= score <= 1.0:
        raise ValueError("quality profile score must be between 0 and 1")
    sample_count = value.get("sample_count")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 1:
        raise ValueError("quality profile sample_count must be a positive integer")
    return QualityProfileEntry(
        provider=provider,
        model=model,
        task_class=task_value,  # type: ignore[arg-type]
        score=score,
        sample_count=sample_count,
    )


def quality_profiles_from_dict(data: object) -> QualityProfiles:
    if not isinstance(data, dict):
        raise ValueError("quality profile document must be an object")
    if data.get("schema_version") != 1:
        raise ValueError("quality profile schema_version must be 1")
    benchmark_id = _required_text(data, "benchmark_id")
    benchmark_version = _required_text(data, "benchmark_version")
    source = _required_text(data, "source")
    metric = _required_text(data, "metric")
    raw_entries = data.get("profiles")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("quality profile profiles must be a non-empty list")
    entries = tuple(_entry(item, index) for index, item in enumerate(raw_entries, start=1))
    keys = [(entry.provider, entry.model, entry.task_class) for entry in entries]
    if len(set(keys)) != len(keys):
        raise ValueError("quality profile entries must be unique by provider/model/task_class")
    return QualityProfiles(
        benchmark_id=benchmark_id,
        benchmark_version=benchmark_version,
        source=source,
        metric=metric,
        entries=entries,
    )


def load_quality_profiles(path: Path) -> QualityProfiles:
    return quality_profiles_from_dict(json.loads(path.read_text(encoding="utf-8")))
