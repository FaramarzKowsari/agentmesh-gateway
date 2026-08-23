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

These are intentionally outside the verified v0.2/v0.3 surface rather than false release blockers:

- [ ] cross-vendor reasoning translation
- [ ] cross-vendor translation of Responses-native built-in tools
- [ ] image/audio normalization across protocols
- [ ] websocket Responses sampling
- [ ] complete Codex authentication, compaction, memory, multi-agent, CLI, and SDK coverage
- [ ] Claude Code-compatible contract suite
- [ ] Cline and OpenCode compatibility fixtures
- [ ] per-client model aliases
- [ ] vision/audio/context-length capability dimensions after the normalized request model supports them

## v0.3 — Adaptive router

- [x] observed token-normalized cost accounting with explicit per-million prices
- [x] bounded latency distribution / p50 / p95 tracking
- [x] deterministic local request-quota windows and hard exhaustion gate
- [x] explicit capability gate for text, tools, reasoning, and native Responses tools
- [x] deterministic semantic task classes for text/tool/reasoning/native-tool requests
- [x] provenance-checked benchmark quality-profile schema
- [x] deterministic no-network policy simulation CLI with JSON/CSV output
- [x] offline `adaptive_balanced` constrained multi-objective baseline
- [x] offline `constrained_ucb` contextual experimental baseline with chosen-only feedback

## v0.4 — Control plane and expanded evidence

- [ ] Web dashboard
- [ ] encrypted local secret store
- [ ] provider validation UI
- [ ] SQLite/PostgreSQL persistence
- [ ] Prometheus and OpenTelemetry exporters
- [ ] audit log
- [ ] real reproducible benchmark trace/profile publication
- [ ] vision/audio/context capability expansion when representable losslessly

## v0.5 — Distribution

- [ ] Windows/macOS/Linux installers
- [ ] signed container images
- [ ] Helm chart
- [ ] SBOM and provenance attestations
- [ ] plugin SDK
