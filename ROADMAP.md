# Roadmap

## v0.1 — Foundation

- [x] protocol-neutral request/response model
- [x] OpenAI-compatible ingress
- [x] Anthropic-compatible ingress
- [x] generic OpenAI-compatible provider adapter
- [x] Anthropic provider adapter
- [x] provider registry
- [x] ordered / latency / cost / quality / balanced routing
- [x] circuit breaker and fallback
- [x] health, readiness and provider-state endpoints
- [x] bearer gateway authentication
- [x] Docker and GitHub Actions
- [x] deterministic tests
- [x] Codex `AGENTS.md`

## v0.2 — Agent compatibility

- [x] OpenAI Responses-shaped ingress with HTTP/SSE text streaming
- [x] custom function-call and function-result normalization across Responses, Chat Completions, and Anthropic Messages
- [x] streamed custom function-call argument translation and continuation
- [x] deterministic Codex custom-provider contract harness for text and custom-function turns
- [x] native `responses` upstream adapter for semantics that must not be downgraded
- [x] native preservation of Responses reasoning controls and encrypted reasoning items
- [x] native preservation of recognized Responses built-in tool definitions and SSE lifecycle events
- [x] capability-aware native-only routing and explicit unsupported-feature gates
- [x] failover safety before stream commitment with no silent provider switch after commitment
- [x] release smoke verification and CI on Python 3.11, 3.12, and 3.13

## Deferred compatibility backlog

These are intentionally outside the verified v0.2 release surface rather than false blockers for v0.2:

- [ ] cross-vendor reasoning translation
- [ ] cross-vendor translation of Responses-native built-in tools
- [ ] image/audio normalization across protocols
- [ ] websocket Responses sampling
- [ ] complete Codex authentication, compaction, memory, multi-agent, CLI, and SDK coverage
- [ ] Claude Code-compatible contract suite
- [ ] Cline and OpenCode compatibility fixtures
- [ ] per-client model aliases

## v0.3 — Adaptive router

- [ ] token-normalized cost accounting
- [ ] EWMA latency percentiles
- [ ] quota window tracking
- [x] explicit capability gate for text, tools, reasoning, and native Responses tools
- [ ] extend capability requirements to vision/context length after the normalized request model supports them
- [ ] task classifier
- [ ] benchmark-derived quality profiles
- [ ] policy simulation CLI

## v0.4 — Control plane

- [ ] Web dashboard
- [ ] encrypted local secret store
- [ ] provider validation UI
- [ ] SQLite/PostgreSQL persistence
- [ ] Prometheus and OpenTelemetry exporters
- [ ] audit log

## v0.5 — Distribution

- [ ] Windows/macOS/Linux installers
- [ ] signed container images
- [ ] Helm chart
- [ ] SBOM and provenance attestations
- [ ] plugin SDK
