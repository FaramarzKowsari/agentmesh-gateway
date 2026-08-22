# Architecture

AgentMesh uses explicit boundaries: `schemas.py` owns ingress validation and canonical conversion; `domain.py` owns provider-neutral models and the provider contract; `providers.py` owns upstream HTTP protocols; `routing.py` owns selection, retries, and fallback; `resilience.py` owns circuit state; `config.py` owns environment parsing; and `app.py` composes runtime dependencies, authentication, error rendering, streaming, and endpoints.

The request path is ingress → canonical request → ranked eligible providers → bounded attempts/fallback → canonical response → protocol response. Provider scoring is deterministic configured metadata. Balanced routing uses in-process selection counts. Circuit state and health are process-local in v0.1.

## Decisions

- Canonical models prevent public wire formats from leaking into routing.
- A structural `Provider` protocol allows adapters and test doubles without inheritance.
- Authentication is enforced as an ingress dependency; credentials never enter domain requests.
- Telemetry has no exporter by default. FastAPI middleware/lifecycle hooks are the intended extension seam.
- Streaming has an async-iterator provider contract; Responses SSE is the first public implementation.

Formal decisions live under `docs/adr/`.
