from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True, frozen=True)
class FunctionCall:
    call_id: str
    name: str
    arguments: str


@dataclass(slots=True, frozen=True)
class FunctionCallDelta:
    index: int
    call_id: str | None = None
    name: str | None = None
    arguments_delta: str = ""


@dataclass(slots=True, frozen=True)
class ReasoningControls:
    effort: str | None = None
    summary: str | None = None
    context: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {
            key: value
            for key, value in (
                ("effort", self.effort),
                ("summary", self.summary),
                ("context", self.context),
            )
            if value is not None
        }


@dataclass(slots=True, frozen=True)
class ResponsesControls:
    instructions: str | None = None
    reasoning: ReasoningControls | None = None
    include: tuple[str, ...] = ()
    prompt_cache_key: str | None = None
    service_tier: str | None = None
    text: dict[str, Any] | None = None
    stream_options: dict[str, Any] | None = None
    client_metadata: dict[str, Any] | None = None
    tool_choice: object | None = None
    parallel_tool_calls: bool | None = None
    store: bool | None = None
    raw_input: object = ""
    requires_native: bool = False


@dataclass(slots=True, frozen=True)
class Message:
    role: Role
    content: str
    tool_calls: tuple[FunctionCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(slots=True, frozen=True)
class NormalizedRequest:
    model: str
    messages: tuple[Message, ...]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False
    tools: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    responses: ResponsesControls | None = None


@dataclass(slots=True, frozen=True)
class NormalizedResponse:
    provider: str
    model: str
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_id: str | None = None
    tool_calls: tuple[FunctionCall, ...] = ()
    native_responses: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class StreamChunk:
    provider: str
    model: str
    text: str = ""
    done: bool = False
    function_call_delta: FunctionCallDelta | None = None
    native_responses_event: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
