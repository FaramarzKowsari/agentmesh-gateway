# AgentMesh Gateway

**AgentMesh Gateway** is an independent, protocol-aware gateway for coding agents and AI models. It gives tools such as Codex, Claude Code-compatible clients, Cline, OpenCode, IDE extensions, scripts, and internal services one stable endpoint while routing requests across cloud and local providers.

This repository is an original implementation. It does not copy source code, documentation, visual assets, or internal naming from `free-claude-code` or any other gateway project. See [PROVENANCE.md](PROVENANCE.md).

## Why this exists

Coding agents increasingly depend on different APIs, quotas, model families, latency profiles, and local runtimes. AgentMesh separates the **client contract** from the **provider contract** and adds a control layer for:

- OpenAI-compatible and Anthropic-compatible ingress
- provider plugins and local runtimes
- automatic fallback and circuit breaking
- latency-, cost-, and quality-aware routing
- health and readiness reporting
- request IDs and structured diagnostics
- optional bearer authentication
- deterministic unit tests with no external API key

## Current status

`v0.1.0` is the foundation release. It contains a working HTTP gateway, provider registry, OpenAI-compatible upstream adapter, Anthropic upstream adapter, routing policies, circuit breaker, fallback execution, admin health endpoint, Docker packaging, CI, and a Codex-ready repository harness.

The next milestones are recorded in [ROADMAP.md](ROADMAP.md).

## Architecture

```text
Coding agents / IDEs / apps
           |
           v
+---------------------------+
| Ingress API               |
| OpenAI + Anthropic shapes |
+---------------------------+
           |
           v
+---------------------------+
| Gateway execution engine  |
| IDs · auth · fallback     |
+---------------------------+
           |
           v
+---------------------------+
| Policy router             |
| health · latency · cost   |
+---------------------------+
           |
           v
+---------------------------+
| Provider adapters         |
| cloud · local · generic   |
+---------------------------+
```

Detailed design: [ARCHITECTURE.md](ARCHITECTURE.md).

## Quick start

### Local Python

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
cp .env.example .env
agentmesh serve --reload
```

The default configuration points at an OpenAI-compatible Ollama endpoint on `http://127.0.0.1:11434/v1`. You can replace it with any configured provider.

### Docker

```bash
docker compose up --build
```

### Health

```bash
curl http://127.0.0.1:8787/healthz
curl http://127.0.0.1:8787/readyz
```

### OpenAI-compatible request

```bash
curl http://127.0.0.1:8787/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Write a Python hello world"}]
  }'
```

### Configure providers

Set `AGENTMESH_PROVIDERS_JSON` to a JSON array. API keys are referenced by environment-variable name, never embedded in the config.

```json
[
  {
    "name": "primary",
    "adapter": "openai",
    "base_url": "https://api.example.com/v1",
    "api_key_env": "PRIMARY_API_KEY",
    "models": ["model-a"],
    "cost_hint": 0.5,
    "quality_hint": 0.9
  },
  {
    "name": "local",
    "adapter": "openai",
    "base_url": "http://host.docker.internal:11434/v1",
    "models": ["qwen2.5-coder:7b"],
    "cost_hint": 0.0,
    "quality_hint": 0.6
  }
]
```

Routing policy values: `balanced`, `latency`, `cost`, `quality`, or `ordered`.

## Security model

If `AGENTMESH_GATEWAY_TOKEN` is set, all `/v1/*` requests require:

```text
Authorization: Bearer <token>
```

Provider secrets stay in environment variables. Error messages are scrubbed before they are returned to callers.

## Development

```bash
ruff check .
pytest
```

Codex instructions live in [AGENTS.md](AGENTS.md). Engineering decisions are recorded under [`docs/adr/`](docs/adr/).

## License

Apache License 2.0. See [LICENSE](LICENSE).
