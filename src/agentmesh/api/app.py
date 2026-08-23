from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agentmesh import __version__
from agentmesh.api.security import require_gateway_token
from agentmesh.config import Settings
from agentmesh.errors import ClientRequestError, NoProviderAvailable, ProviderError
from agentmesh.gateway.service import GatewayService
from agentmesh.protocols.anthropic import parse_anthropic_request, render_anthropic_response
from agentmesh.protocols.openai import parse_openai_request, render_openai_response
from agentmesh.protocols.responses import parse_responses_request
from agentmesh.protocols.responses_native import (
    attach_responses_controls,
    render_responses_or_native,
    render_responses_stream_or_native,
)
from agentmesh.protocols.responses_validation import validate_responses_payload
from agentmesh.providers.registry import ProviderRegistry
from agentmesh.routing.router import Router
from agentmesh.routing.state import RuntimeStateStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    registry = ProviderRegistry(settings.providers)
    states = RuntimeStateStore([spec.name for spec in settings.providers])
    router = Router(settings.providers, states, settings.routing_policy)
    gateway = GatewayService(
        registry,
        router,
        states,
        max_attempts=settings.max_attempts,
        failure_threshold=settings.failure_threshold,
        cooldown_seconds=settings.cooldown_seconds,
    )

    app = FastAPI(title="AgentMesh Gateway", version=__version__)
    app.state.settings = settings
    app.state.registry = registry
    app.state.states = states
    app.state.gateway = gateway

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(ClientRequestError)
    async def client_error_handler(_request: Request, exc: ClientRequestError) -> JSONResponse:
        error: dict[str, object] = {
            "type": "invalid_request_error",
            "code": exc.code,
            "message": str(exc),
        }
        if exc.feature is not None:
            error["feature"] = exc.feature
        return JSONResponse(status_code=400, content={"error": error})

    @app.exception_handler(ProviderError)
    async def provider_error_handler(_request: Request, exc: ProviderError) -> JSONResponse:
        status = 502 if exc.retryable else (exc.status_code or 400)
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "type": "provider_error",
                    "message": str(exc),
                    "provider": exc.provider,
                    "retryable": exc.retryable,
                }
            },
        )

    @app.exception_handler(NoProviderAvailable)
    async def unavailable_handler(_request: Request, exc: NoProviderAvailable) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": {"message": str(exc)}})

    @app.get("/healthz")
    async def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    async def ready() -> dict[str, object]:
        available = [name for name, state in states.snapshot().items() if state.available()]
        if not available:
            raise HTTPException(status_code=503, detail="no provider circuit is available")
        return {"status": "ready", "providers": available}

    @app.get("/admin/providers", dependencies=[Depends(require_gateway_token)])
    async def provider_states() -> dict[str, object]:
        result: dict[str, object] = {}
        for spec in settings.providers:
            state = states.get(spec.name)
            result[spec.name] = {
                "adapter": spec.adapter,
                "models": list(spec.models),
                "capabilities": sorted(spec.effective_capabilities()),
                "available": state.available(),
                "successes": state.successes,
                "failures": state.failures,
                "latency_ewma_ms": state.latency_ewma_ms,
                "last_error": state.last_error,
            }
        return result

    @app.get("/v1/models", dependencies=[Depends(require_gateway_token)])
    async def models() -> dict[str, object]:
        rows = []
        seen: set[str] = set()
        for spec in settings.providers:
            for model in spec.models:
                if model not in seen:
                    rows.append({"id": model, "object": "model", "owned_by": spec.name})
                    seen.add(model)
        rows.insert(0, {"id": "auto", "object": "model", "owned_by": "agentmesh"})
        return {"object": "list", "data": rows}

    @app.post("/v1/chat/completions", dependencies=[Depends(require_gateway_token)])
    async def openai_chat(payload: dict[str, Any]):
        normalized = parse_openai_request(payload)
        if normalized.stream:
            gateway.ensure_eligible(normalized)

            async def generate():  # type: ignore[no-untyped-def]
                async for chunk in gateway.stream(normalized):
                    if chunk.done:
                        yield "data: [DONE]\n\n"
                        continue
                    event = {
                        "id": f"chatcmpl-{uuid.uuid4().hex}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": chunk.model,
                        "provider": chunk.provider,
                        "choices": [{"index": 0, "delta": {"content": chunk.text}}],
                    }
                    yield f"data: {json.dumps(event)}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")
        response = await gateway.complete(normalized)
        return render_openai_response(response)

    @app.post("/v1/responses", dependencies=[Depends(require_gateway_token)])
    async def responses_api(payload: dict[str, Any]):
        validate_responses_payload(payload)
        normalized = attach_responses_controls(parse_responses_request(payload), payload)
        if normalized.stream:
            gateway.ensure_eligible(normalized)
            events = render_responses_stream_or_native(
                gateway.stream(normalized),
                normalized.model,
            )
            return StreamingResponse(events, media_type="text/event-stream")
        response = await gateway.complete(normalized)
        return render_responses_or_native(response)

    @app.post("/v1/messages", dependencies=[Depends(require_gateway_token)])
    async def anthropic_messages(payload: dict[str, Any]):
        normalized = parse_anthropic_request(payload)
        if normalized.stream:
            gateway.ensure_eligible(normalized)

            async def generate():  # type: ignore[no-untyped-def]
                async for chunk in gateway.stream(normalized):
                    if chunk.done:
                        event = {"type": "message_stop"}
                    else:
                        event = {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": chunk.text},
                        }
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")
        response = await gateway.complete(normalized)
        return render_anthropic_response(response)

    return app


app = create_app()
