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
from agentmesh.errors import NoProviderAvailable, ProviderError
from agentmesh.gateway.service import GatewayService
from agentmesh.protocols.anthropic import parse_anthropic_request, render_anthropic_response
from agentmesh.protocols.openai import parse_openai_request, render_openai_response
from agentmesh.protocols.responses import (
    parse_responses_request,
    render_responses_response,
    response_envelope,
)
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
        available = [
            name for name, state in states.snapshot().items() if state.available()
        ]
        if not available:
            raise HTTPException(status_code=503, detail="no provider circuit is available")
        return {"status": "ready", "providers": available}

    @app.get("/admin/providers")
    async def provider_states() -> dict[str, object]:
        result: dict[str, object] = {}
        for spec in settings.providers:
            state = states.get(spec.name)
            result[spec.name] = {
                "adapter": spec.adapter,
                "models": list(spec.models),
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
        normalized = parse_responses_request(payload)
        if normalized.stream:
            async def generate():  # type: ignore[no-untyped-def]
                response_id = f"resp_{uuid.uuid4().hex}"
                item_id = f"msg_{uuid.uuid4().hex}"
                sequence = 0
                created = response_envelope(
                    response_id,
                    normalized.model,
                    status="in_progress",
                    output=[],
                )
                created_event = {
                    "type": "response.created",
                    "response": created,
                    "sequence_number": sequence,
                }
                yield (
                    "event: response.created\n"
                    f"data: {json.dumps(created_event)}\n\n"
                )
                sequence += 1
                added_item = {
                    "type": "message",
                    "id": item_id,
                    "status": "in_progress",
                    "role": "assistant",
                    "content": [],
                }
                event = {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": added_item,
                    "sequence_number": sequence,
                }
                yield f"event: response.output_item.added\ndata: {json.dumps(event)}\n\n"
                sequence += 1
                accumulated: list[str] = []
                provider_name = None
                model_name = normalized.model
                async for chunk in gateway.stream(normalized):
                    provider_name = chunk.provider
                    model_name = chunk.model
                    if chunk.done:
                        continue
                    accumulated.append(chunk.text)
                    event = {
                        "type": "response.output_text.delta",
                        "item_id": item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": chunk.text,
                        "sequence_number": sequence,
                    }
                    yield f"event: response.output_text.delta\ndata: {json.dumps(event)}\n\n"
                    sequence += 1
                text = "".join(accumulated)
                done = {
                    "type": "response.output_text.done",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "text": text,
                    "sequence_number": sequence,
                }
                yield f"event: response.output_text.done\ndata: {json.dumps(done)}\n\n"
                sequence += 1
                output_item = {
                    "type": "message",
                    "id": item_id,
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text, "annotations": []}],
                }
                completed = response_envelope(
                    response_id,
                    model_name,
                    status="completed",
                    output=[output_item],
                    provider=provider_name,
                )
                event = {
                    "type": "response.completed",
                    "response": completed,
                    "sequence_number": sequence,
                }
                yield f"event: response.completed\ndata: {json.dumps(event)}\n\n"
            return StreamingResponse(generate(), media_type="text/event-stream")
        response = await gateway.complete(normalized)
        return render_responses_response(response)

    @app.post("/v1/messages", dependencies=[Depends(require_gateway_token)])
    async def anthropic_messages(payload: dict[str, Any]):
        normalized = parse_anthropic_request(payload)
        if normalized.stream:
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
