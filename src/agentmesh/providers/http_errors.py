from __future__ import annotations

import httpx

from agentmesh.errors import ProviderError

RETRYABLE_STATUS = {408, 409, 425, 429}


def translate_http_error(provider: str, exc: httpx.HTTPError) -> ProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        retryable = status in RETRYABLE_STATUS or status >= 500
        message = f"upstream returned HTTP {status}"
        return ProviderError(message, provider=provider, retryable=retryable, status_code=status)
    return ProviderError("upstream network failure", provider=provider, retryable=True)
