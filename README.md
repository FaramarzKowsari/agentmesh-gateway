# AgentMesh Gateway

**AgentMesh Gateway** is an independent, protocol-aware gateway for coding agents, AI clients, and model services. It exposes stable OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages-shaped endpoints while routing requests across local and remote providers with health-aware fallback and policy routing.

The project is an original implementation. It does not copy source code, documentation, assets, internal naming, or commit history from `free-claude-code` or another gateway project. See [PROVENANCE.md](PROVENANCE.md).

## v0.2.0 at a glance

The v0.2 line turns the v0.1 routing foundation into a tested agent-protocol gateway:

- OpenAI Chat Completions-shaped ingress
- OpenAI Responses-shaped ingress with HTTP/SSE streaming
- Anthropic Messages-shaped ingress
- generic OpenAI-compatible Chat Completions upstreams
- Anthropic Messages upstreams
- native Responses-compatible upstreams for semantics that must not be downgraded
- ordered, latency, cost, quality, and balanced routing policies
- retry/fallback before stream commitment, with no silent provider switch after output begins
- circuit breaking, health/readiness endpoints, request IDs, and provider-state diagnostics
- custom function-call normalization across Responses, Chat Completions, and Anthropic Messages
- streamed function-call argument handling
- lossless native preservation of Responses reasoning controls and encrypted reasoning items
- native preservation of recognized Responses built-in tool definitions and tool lifecycle events
- deterministic Codex custom-provider contract tests for text, custom-function loops, native reasoning, and native tools
- local-first default configuration using an OpenAI-compatible Ollama endpoint
- tests that require no paid API, provider key, or external provider call

AgentMesh deliberately distinguishes **translated compatibility** from **native preservation**. If a request contains semantics that cannot be translated without loss, only a native `responses` provider is eligible. The gateway returns a clear error instead of manufacturing an equivalent-looking request.

## Adaptive routing work on `main`

The v0.3 router work starts with explicit provider capability constraints. Routing now separates **feasibility** from **optimization**: a provider must satisfy protocol, model, health, and capability requirements before latency/cost/quality scoring can rank it.

The initial declared capability vocabulary is intentionally limited to behavior AgentMesh can currently derive from a normalized request:

- `text`
- `tools`
- `reasoning`
- `native_responses_tools`

This is a hard gate, not a score hint. For example, a provider explicitly configured with only `text` cannot win a custom-tool request even if it is the cheapest provider.

## What v0.2.0 does not claim

This is not a claim of full OpenAI Responses or full Codex compatibility. v0.2.0 does **not** claim:

- cross-vendor reasoning translation
- cross-vendor translation of Responses-native built-in tools
- websocket Responses sampling
- image/audio normalization across protocols
- complete prompt-cache semantic translation
- every Codex authentication, compaction, memory, multi-agent, CLI, or SDK feature
- complete Claude Code, Cline, or OpenCode client contract coverage

The verified boundary is maintained in [docs/product-specs/compatibility.md](docs/product-specs/compatibility.md). Codex-specific evidence and limits are documented in [docs/CODEX_COMPATIBILITY.md](docs/CODEX_COMPATIBILITY.md).

## Architecture

```text
Coding clients / IDEs / services
              |
              v
+----------------------------------+
| Protocol ingress                 |
| Chat Completions | Responses     |
| Anthropic Messages               |
+----------------------------------+
              |
              v
+----------------------------------+
| Normalization + feasibility      |
| protocol | model | capabilities  |
+----------------------------------+
              |
              v
+----------------------------------+
| Policy router + execution engine |
| health | score | fallback        |
+----------------------------------+
              |
              v
+----------------------------------+
| Provider adapters                |
| Chat | Anthropic | Responses     |
| local or remote                  |
+----------------------------------+
```

Detailed design: [ARCHITECTURE.md](ARCHITECTURE.md). Capability routing is recorded in [ADR 0003](docs/adr/0003-capability-aware-routing.md).

## Quick start: local Ollama, no paid API key

Requirements: Python 3.11+ and an OpenAI-compatible local server. The default configuration targets Ollama at `http://127.0.0.1:11434/v1` with `qwen2.5-coder:7b`.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
agentmesh version
agentmesh serve
```

If you use Ollama, make sure the configured model exists locally, for example:

```bash
ollama pull qwen2.5-coder:7b
```

The gateway listens on `127.0.0.1:8787` by default.

```bash
curl http://127.0.0.1:8787/healthz
curl http://127.0.0.1:8787/readyz
```

A basic Chat Completions-shaped request:

```bash
curl http://127.0.0.1:8787/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Write a Python hello world"}]
  }'
```

## Provider configuration

Provider configuration is supplied through `AGENTMESH_PROVIDERS_JSON`. `api_key_env` names an environment variable; secrets are not embedded in the provider JSON.

Three adapter types are available:

| Adapter | Upstream wire contract | Primary use |
| --- | --- | --- |
| `openai` | Chat Completions-compatible | local runtimes and generic OpenAI-compatible providers |
| `anthropic` | Anthropic Messages | Anthropic-compatible providers |
| `responses` | OpenAI Responses-compatible | lossless Responses-specific semantics |

Example with explicit capability restrictions:

```bash
export AGENTMESH_PROVIDERS_JSON='[
  {
    "name": "local-text",
    "adapter": "openai",
    "base_url": "http://127.0.0.1:11434/v1",
    "models": ["qwen2.5-coder:7b"],
    "capabilities": ["text"],
    "cost_hint": 0.0,
    "quality_hint": 0.6
  },
  {
    "name": "native-responses",
    "adapter": "responses",
    "base_url": "https://api.example.com/v1",
    "api_key_env": "RESPONSES_API_KEY",
    "models": ["model-with-responses-support"],
    "capabilities": ["text", "tools", "reasoning", "native_responses_tools"],
    "cost_hint": 0.5,
    "quality_hint": 0.9
  }
]'
```

Routing policies are `balanced`, `latency`, `cost`, `quality`, and `ordered`.

### Capability defaults and restrictions

`capabilities` is optional for backward compatibility. If it is omitted, AgentMesh derives the same assumptions used before explicit capability routing:

| Adapter | Default effective capabilities |
| --- | --- |
| `openai` | `text`, `tools` |
| `anthropic` | `text`, `tools` |
| `responses` | `text`, `tools`, `reasoning`, `native_responses_tools` |

If `capabilities` is supplied, the list is authoritative. Use explicit capabilities when a particular model is more limited than its wire adapter. Effective capabilities are visible at the authenticated `/admin/providers` endpoint.

The router currently does not advertise vision, audio, or context-window capability routing. Those dimensions remain roadmap items until the normalized request model can express and test them reliably.

The repository includes [.env.example](.env.example). Docker Compose consumes `.env` through `env_file`; a direct local Python process uses the environment of the shell that launches `agentmesh`.

## Responses routing behavior

A Responses request containing only semantics that AgentMesh can translate may route to an `openai` or eligible `anthropic` adapter. Custom `function` tools are part of this translated surface.

Requests that carry Responses-specific semantics such as reasoning controls, encrypted reasoning items, Responses text/stream controls, or recognized non-function native tools are marked **native-only**. They require an adapter of type `responses`. If no eligible native provider exists, AgentMesh returns an error before streaming headers are committed.

Capabilities add a second feasibility gate. A native Responses adapter can still be excluded if its explicit capability list does not contain the requirements derived from the request.

Unknown tool/input types are rejected explicitly rather than silently discarded.

## Codex custom-provider contract

AgentMesh tests the public Codex custom-provider boundary with a local deterministic fixture. The tested configuration shape is:

```toml
model = "m"
model_provider = "agentmesh"

[model_providers.agentmesh]
name = "AgentMesh Gateway"
base_url = "http://127.0.0.1:8787/v1"
wire_api = "responses"
supports_websockets = false
```

Replace `m` with a model advertised by your AgentMesh provider configuration. The fixture is in [`tests/fixtures/codex/config.toml`](tests/fixtures/codex/config.toml).

The contract suite verifies the HTTP/SSE wire boundary; it is intentionally narrower than a statement of complete Codex compatibility.

## Docker

Copy the example environment file before starting Compose:

```bash
cp .env.example .env
docker compose up --build
```

The container binds AgentMesh to `0.0.0.0:8787` and Compose publishes port `8787`. Treat that as network exposure, not as a development-only loopback bind.

## Security model

For loopback-only development, authentication is optional. If the gateway is reachable by another machine, set a strong `AGENTMESH_GATEWAY_TOKEN` and apply normal host/network controls.

When `AGENTMESH_GATEWAY_TOKEN` is set, requests to `/v1/*` and `/admin/providers` require:

```text
Authorization: Bearer <token>
```

`/healthz` and `/readyz` remain unauthenticated so orchestrators can probe the service. Provider secrets remain in environment variables. Provider error bodies are normalized before being returned to callers.

Do not publish port `8787` to an untrusted network without authentication and network-layer restrictions.

## Development and verification

```bash
ruff check .
pytest
```

CI runs the same lint/test gates on Python 3.11, 3.12, and 3.13. Contract tests use mock transports and do not require a live provider.

Engineering guidance is in [AGENTS.md](AGENTS.md); design decisions live under [`docs/adr/`](docs/adr/).

## Release notes and roadmap

- [CHANGELOG.md](CHANGELOG.md)
- [RELEASE_NOTES_v0.2.0.md](RELEASE_NOTES_v0.2.0.md)
- [ROADMAP.md](ROADMAP.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
