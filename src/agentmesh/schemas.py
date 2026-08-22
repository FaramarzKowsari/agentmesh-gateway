"""Ingress protocol schemas and canonical conversion."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from .domain import CanonicalMessage, CanonicalRequest


class OpenAIMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[OpenAIMessage] = Field(min_length=1)
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float | None = None
    stream: bool = False

    def canonical(self) -> CanonicalRequest:
        return CanonicalRequest(model=self.model, messages=[CanonicalMessage(**m.model_dump()) for m in self.messages], max_tokens=self.max_tokens, temperature=self.temperature, stream=self.stream)


class ResponsesRequest(BaseModel):
    model: str
    input: str | list[dict[str, Any]]
    max_output_tokens: int | None = Field(default=None, gt=0)
    stream: bool = False

    def canonical(self) -> CanonicalRequest:
        if isinstance(self.input, str):
            messages = [CanonicalMessage(role="user", content=self.input)]
        else:
            messages = [CanonicalMessage(role=str(item.get("role", "user")), content=str(item.get("content", ""))) for item in self.input]
        return CanonicalRequest(model=self.model, messages=messages, max_tokens=self.max_output_tokens, stream=self.stream)


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class MessagesRequest(BaseModel):
    model: str
    messages: list[AnthropicMessage] = Field(min_length=1)
    max_tokens: int = Field(gt=0)
    system: str | None = None
    stream: bool = False

    def canonical(self) -> CanonicalRequest:
        messages = ([CanonicalMessage(role="system", content=self.system)] if self.system else []) + [CanonicalMessage(**m.model_dump()) for m in self.messages]
        return CanonicalRequest(model=self.model, messages=messages, max_tokens=self.max_tokens, stream=self.stream)
