# AgentMesh Gateway

AgentMesh Gateway is an independently developed, local-first HTTP gateway that gives applications a stable API while selecting among OpenAI-compatible and Anthropic upstreams. Version 0.1.0 focuses on a small production-oriented foundation, not feature parity with every provider.

## Supported surfaces

- Health: `GET /health`, `GET /ready`
- OpenAI-compatible: `POST /v1/chat/completions`, `POST /v1/responses`, `GET /v1/models`
- Anthropic-compatible: `POST /v1/messages`
- Administration: `GET /admin/providers`, `GET /admin/status`
- Deterministic OpenAI Responses SSE text events

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn agentmesh.app:app --reload
curl http://127.0.0.1:8000/health
```

The gateway is healthy without providers but reports not ready until at least one is configured. Provider configuration is a JSON array in `AGENTMESH_PROVIDERS`; API keys are optional for compatible local servers.

```bash
curl http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello"}]}'
curl http://127.0.0.1:8000/v1/responses -H 'Content-Type: application/json' \
  -d '{"model":"auto","input":"Hello","stream":true}'
```

## Architecture and routing

Ingress schemas translate public protocols into canonical messages. A protocol-independent router ranks provider adapters, retries bounded failures, falls back, and records circuit state. Composition remains in the FastAPI application. See [ARCHITECTURE.md](ARCHITECTURE.md).

Set `AGENTMESH_ROUTING_STRATEGY` to `ordered`, `balanced`, `cost`, `latency`, or `quality`. `auto` selects the first model advertised by the winning provider. Scores use configured metadata. Add a provider by implementing the typed `Provider` protocol, then instantiate it at composition time; routing requires no modification.

## Security

Set `AGENTMESH_BEARER_TOKEN` to require `Authorization: Bearer …` on API and admin routes. Health probes remain unauthenticated. Secrets use Pydantic secret values, errors are normalized, and telemetry is not exported. Read [SECURITY.md](SECURITY.md) and [the threat model](docs/threat-model.md) before exposing the service beyond localhost.

See [ROADMAP.md](ROADMAP.md) for planned compatibility and operational work and [CONTRIBUTING.md](CONTRIBUTING.md) for development commands.
