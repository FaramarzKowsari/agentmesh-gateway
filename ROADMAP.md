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

- [x] text-only OpenAI Responses API ingress and core streaming events
- [ ] full Responses API tools/reasoning/image lifecycle compatibility
- [ ] complete Anthropic tool-use conversion
- [ ] Codex CLI compatibility test harness
- [ ] Claude Code-compatible contract test harness
- [ ] Cline and OpenCode compatibility fixtures
- [ ] per-client model aliases

## v0.3 — Adaptive router

- [ ] token-normalized cost accounting
- [ ] EWMA latency percentiles
- [ ] quota window tracking
- [ ] capability tags (vision, tools, reasoning, context length)
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
