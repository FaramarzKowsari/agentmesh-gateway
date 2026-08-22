"""Environment-backed configuration."""

import json
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderSettings(BaseModel):
    name: str
    kind: Literal["openai", "anthropic"]
    base_url: str
    api_key: SecretStr | None = None
    models: list[str] = Field(default_factory=list)
    priority: int = 100
    cost: float = Field(default=1, ge=0)
    latency: float = Field(default=1, ge=0)
    quality: float = Field(default=1, ge=0)
    timeout_seconds: float = Field(default=30, gt=0)
    max_attempts: int = Field(default=2, ge=1, le=5)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTMESH_", env_file=".env", extra="ignore")

    providers: list[ProviderSettings] = Field(default_factory=list)
    routing_strategy: Literal["ordered", "balanced", "cost", "latency", "quality"] = "ordered"
    bearer_token: SecretStr | None = None
    circuit_failure_threshold: int = Field(default=3, ge=1)
    circuit_recovery_seconds: float = Field(default=30, gt=0)

    @field_validator("providers", mode="before")
    @classmethod
    def parse_providers(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value
