from __future__ import annotations


class AgentMeshError(Exception):
    """Base error for gateway failures."""


class ConfigurationError(AgentMeshError):
    """Raised for invalid gateway configuration."""


class ClientRequestError(AgentMeshError):
    """Raised when a client requests unsupported or invalid protocol semantics."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_request",
        feature: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.feature = feature


class ProviderError(AgentMeshError):
    """Normalized provider failure."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code


class NoProviderAvailable(AgentMeshError):
    """Raised when no configured provider can serve a request."""
