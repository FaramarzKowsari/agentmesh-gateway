from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request


async def require_gateway_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    token = request.app.state.settings.gateway_token
    if not token:
        return
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="invalid gateway credentials")
