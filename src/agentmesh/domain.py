from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True, frozen=True)
class Message:
    role: Role
    content: str


@dataclass(slots=True, frozen=True)
class NormalizedRequest:
    model: str
    messages: tuple[Message, ...]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False
    tools: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class NormalizedResponse:
    provider: str
    model: str
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_id: str | None = None


@dataclass(slots=True, frozen=True)
class StreamChunk:
    provider: str
    model: str
    text: str
    done: bool = False
