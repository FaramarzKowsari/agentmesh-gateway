# AgentMesh Gateway v0.1.0

Foundation release of the independent universal coding-agent/model gateway.

## Included

- protocol-neutral domain model
- OpenAI Chat Completions ingress
- text-oriented OpenAI Responses ingress and streaming events
- Anthropic Messages ingress
- generic OpenAI-compatible upstream adapter
- Anthropic upstream adapter
- ordered, latency, cost, quality and balanced routing
- retry-aware fallback and per-provider circuit breakers
- optional bearer authentication
- health, readiness, model catalog and provider-state endpoints
- Docker, GitHub Actions, Dependabot, issue/PR templates
- provenance record, threat model, ADRs, execution plan and Codex AGENTS.md
- 16 deterministic tests requiring no paid API key

## Known limits

This release does not claim complete Codex/Claude Code wire compatibility. Full Responses tool/reasoning events, cross-vendor tool translation, image/audio normalization, persistence, dashboard, telemetry exporters and signed release artifacts remain roadmap work.
