# AgentMesh Gateway v0.2.0

v0.2.0 is the agent-protocol compatibility release. It builds on the v0.1 routing foundation by adding a tested OpenAI Responses boundary, Codex custom-provider contract coverage, cross-protocol custom-function translation, and native preservation for Responses semantics that should not be downgraded.

## Highlights

- **Responses ingress:** non-streaming and SSE `/v1/responses` support for the verified text/custom-function surface.
- **Codex contract harness:** deterministic HTTP/SSE tests for a `wire_api = "responses"` custom provider, including text, streamed function calls, `function_call_output` continuation, native reasoning, and native tool preservation.
- **Cross-protocol custom functions:** function schemas, calls, arguments, and results are normalized across Responses, Chat Completions, and Anthropic Messages where the mapping is explicit.
- **Native reasoning preservation:** reasoning controls, prior reasoning items, encrypted reasoning content, include fields, and related Responses controls can be routed through a native `responses` upstream without flattening them into text.
- **Native Responses tools:** recognized non-function Responses tool definitions force native-only routing and their JSON definitions and lifecycle SSE events are preserved without pretending they are ordinary cross-vendor functions.
- **Failover safety:** providers may fall back before the first client-visible stream commitment, but AgentMesh does not silently switch providers after text or tool state has been committed.
- **Local-first path:** default tests require no live API key or paid provider; the documented development path can target a local OpenAI-compatible Ollama endpoint.

## Provider adapters

v0.2.0 exposes three upstream adapter families:

- `openai` — Chat Completions-compatible upstreams
- `anthropic` — Anthropic Messages-compatible upstreams
- `responses` — native Responses-compatible upstreams for loss-sensitive semantics

A request that only uses translatable semantics may route across compatible translated providers. A request that carries Responses-specific semantics that AgentMesh cannot map losslessly is marked native-only. If no eligible native Responses provider exists, the gateway returns an explicit no-eligible-provider error rather than sending a downgraded request.

## Security change

When `AGENTMESH_GATEWAY_TOKEN` is configured, `/v1/*` and `/admin/providers` require bearer authentication. `/healthz` and `/readyz` remain unauthenticated for orchestration probes. Docker publishes a service that binds to `0.0.0.0:8787`; deployments reachable beyond loopback should use a strong gateway token and network-layer controls.

## Verification

The release candidate is gated by:

- `ruff check .`
- `pytest`
- Python 3.11, 3.12, and 3.13 GitHub Actions matrix
- deterministic mock-transport compatibility tests with no live provider dependency
- release smoke checks for package version, CLI version, health version, and local ASGI routes

## Compatibility boundary

This release does **not** claim full OpenAI Responses or full Codex compatibility. Specifically, it does not claim:

- cross-vendor reasoning translation
- cross-vendor translation or local execution of provider-native built-in tools
- websocket Responses sampling
- image/audio normalization across protocols
- complete prompt-cache semantic translation
- every Codex authentication, compaction, memory, multi-agent, CLI, or SDK feature
- complete Claude Code, Cline, or OpenCode compatibility suites

See `docs/product-specs/compatibility.md` and `docs/CODEX_COMPATIBILITY.md` for the verified surface and explicit limits.

## Upgrade notes from v0.1.0

No persistence migration is required. Existing `openai` and `anthropic` provider configurations remain valid. To preserve native Responses-only semantics, add a provider with `"adapter": "responses"` and a Responses-compatible `base_url`.

If the gateway is exposed beyond loopback, set `AGENTMESH_GATEWAY_TOKEN` before treating the deployment as production-like.
