"""FastAPI composition root and protocol ingress adapters."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .config import Settings
from .domain import GatewayError
from .providers import AnthropicProvider, OpenAIProvider
from .routing import Router
from .schemas import ChatRequest, MessagesRequest, ResponsesRequest


def create_app(settings: Settings | None = None, router: Router | None = None) -> FastAPI:
    settings = settings or Settings()
    if router is None:
        providers = [OpenAIProvider(p) if p.kind == "openai" else AnthropicProvider(p) for p in settings.providers]
        max_attempts = max((provider.max_attempts for provider in settings.providers), default=2)
        router = Router(providers, settings.routing_strategy, failure_threshold=settings.circuit_failure_threshold, recovery_seconds=settings.circuit_recovery_seconds, max_attempts=max_attempts)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for provider in router.providers:
            client = getattr(provider, "client", None)
            if client:
                await client.aclose()

    app = FastAPI(title="AgentMesh Gateway", version="0.1.0", lifespan=lifespan)
    app.state.router, app.state.settings = router, settings

    async def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = settings.bearer_token.get_secret_value() if settings.bearer_token else None
        if expected and authorization != f"Bearer {expected}":
            raise GatewayError("Invalid or missing bearer token", code="unauthorized", status=401)

    auth = [Depends(authenticate)]

    @app.exception_handler(GatewayError)
    async def gateway_error(_: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": {"message": exc.message, "type": exc.code}})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        ready_now = bool(router.providers)
        return JSONResponse(status_code=200 if ready_now else 503, content={"status": "ready" if ready_now else "not_ready"})

    @app.post("/v1/chat/completions", dependencies=auth)
    async def chat(body: ChatRequest) -> dict[str, Any]:
        result = await router.execute(body.canonical())
        return {"id": result.id, "object": "chat.completion", "model": result.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": result.text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": result.input_tokens, "completion_tokens": result.output_tokens, "total_tokens": result.input_tokens + result.output_tokens}}

    @app.post("/v1/responses", dependencies=auth)
    async def responses(body: ResponsesRequest) -> Any:
        result = await router.execute(body.canonical())
        payload = {"id": result.id, "object": "response", "status": "completed", "model": result.model, "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": result.text}]}]}
        if not body.stream:
            return payload

        async def events() -> AsyncIterator[str]:
            created = {"type": "response.created", "response": {**payload, "status": "in_progress", "output": []}}
            yield f"data: {json.dumps(created)}\n\n"
            yield f"data: {json.dumps({'type': 'response.output_text.delta', 'delta': result.text})}\n\n"
            yield f"data: {json.dumps({'type': 'response.completed', 'response': payload})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/v1/messages", dependencies=auth)
    async def messages(body: MessagesRequest) -> dict[str, Any]:
        result = await router.execute(body.canonical())
        return {"id": result.id, "type": "message", "role": "assistant", "model": result.model, "content": [{"type": "text", "text": result.text}], "stop_reason": "end_turn", "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens}}

    @app.get("/v1/models", dependencies=auth)
    async def models() -> dict[str, Any]:
        names = sorted({model for provider in router.providers for model in provider.metadata.models})
        return {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "upstream"} for name in names]}

    @app.get("/admin/providers", dependencies=auth)
    async def provider_list() -> list[dict[str, Any]]:
        return [{"name": p.name, "models": list(p.metadata.models), "circuit": router.breakers[p.name].state} for p in router.providers]

    @app.get("/admin/status", dependencies=auth)
    async def status() -> dict[str, Any]:
        return {"version": "0.1.0", "strategy": router.strategy, "providers": len(router.providers), "authentication": bool(settings.bearer_token)}

    return app


app = create_app()
