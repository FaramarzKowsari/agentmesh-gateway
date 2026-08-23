# Changelog

All notable changes to AgentMesh Gateway are documented in this file.

## [Unreleased]

### Added

- Explicit provider capability declarations for `text`, `tools`, `reasoning`, and `native_responses_tools`.
- Capability-aware feasibility filtering before latency/cost/quality/ordered routing policies are applied.
- Effective provider capabilities in `/admin/providers` diagnostics.
- ADR 0003 documenting the capability gate as a hard routing constraint and research foundation for later adaptive policies.
- Optional `input_cost_per_million` and `output_cost_per_million` provider prices in USD per one million tokens.
- Observed input/output token totals, cost totals, observation counts, and last observed usage/cost in provider runtime diagnostics.
- Native Responses streaming usage accounting when exact final usage is present in `response.completed`.
- ADR 0004 defining observed-only accounting and the separation between routing `cost_hint` and measured cost evidence.
- Bounded recent-success latency windows with deterministic nearest-rank p50/p95 diagnostics.
- Configurable latency sample windows for deterministic tests and future policy simulation.
- ADR 0005 documenting why latency distribution evidence remains separate from the current EWMA routing signal.
- Optional deterministic local request-quota windows with hard exhaustion filtering before policy scoring.
- Quota diagnostics for used/remaining attempts, pressure, exhaustion, and reset interval.
- ADR 0006 defining outbound-attempt counting and the distinction between local quota control and vendor-side rate limits.
- Deterministic no-network policy simulation engine over provider JSON and request/outcome JSONL traces.
- `agentmesh simulate` with baseline-policy comparison plus JSON/CSV output for analysis tooling.
- Example simulation fixtures explicitly labeled as mechanics-only rather than benchmark evidence.
- ADR 0007 documenting fresh-state counterfactual policy replay and missing-observation rules.

### Compatibility

- Existing provider configurations that omit `capabilities` keep adapter-derived defaults matching the prior behavior.
- An explicit capability list is authoritative and can restrict a provider from tool, reasoning, or native-tool traffic even when the adapter shape would otherwise be eligible.
- Existing `cost_hint` routing behavior is unchanged; token prices and observed USD costs do not silently change routing scores.
- Missing token usage or missing token prices remain unobserved rather than being treated as zero cost.
- Existing latency and balanced routing behavior remains EWMA-based; adding p50/p95 does not silently change policy objectives.
- Providers without request-quota configuration behave as before. Configured quota pressure is diagnostic; only exhaustion is a hard feasibility gate.
- Simulation reuses runtime feasibility/state semantics without contacting provider `base_url` values.

## [0.2.0] - 2026-08-23

### Added

- OpenAI Responses-shaped ingress with non-streaming and SSE response lifecycles.
- Cross-protocol custom function-call and function-result normalization across Responses, Chat Completions, and Anthropic Messages.
- Streamed custom function-call argument handling and function-output continuation.
- Deterministic Codex custom-provider wire-contract tests for text, custom-function turns, native reasoning, and native Responses tools.
- Native `responses` upstream adapter for request semantics that must not be downgraded.
- Native preservation of Responses reasoning controls, reasoning input items, encrypted reasoning content, include fields, prompt-cache/service-tier controls, text controls, stream options, client metadata, tool choice, parallel-tool-call policy, and store policy.
- Explicit whitelist for recognized Responses-native tool types, with byte-semantic JSON preservation through native Responses upstreams.
- Native built-in-tool SSE event passthrough at `/v1/responses`.
- Capability-aware routing that excludes non-native providers when a Responses request requires native semantics.
- Structured unsupported-feature validation for unknown or non-representable Responses input/tool types.
- Release smoke tests for package, CLI, health endpoint, and local ASGI behavior.

### Changed

- Streaming routes now preflight provider eligibility before response headers are committed.
- Responses-native semantics are preserved at a native boundary instead of being silently flattened into translated protocols.
- Documentation now distinguishes translated compatibility from native protocol preservation.
- `/admin/providers` follows the configured gateway bearer-auth policy.
- Package and runtime version advanced to `0.2.0`.

### Security

- Provider-state diagnostics are protected when `AGENTMESH_GATEWAY_TOKEN` is configured.
- Deployment guidance now calls out Docker's `0.0.0.0:8787` bind and recommends gateway authentication plus network-layer controls for non-loopback deployments.

### Explicit limits

v0.2.0 does not claim full OpenAI Responses or full Codex compatibility. It does not provide cross-vendor reasoning translation, cross-vendor translation or local execution of Responses-native built-in tools, websocket Responses sampling, image/audio normalization across protocols, or complete Codex/Claude Code/Cline/OpenCode contract coverage.

## [0.1.0]

- Initial protocol-neutral gateway foundation.
- OpenAI-compatible and Anthropic ingress/provider adapters.
- Provider registry, policy routing, fallback, circuit breaking, health/readiness endpoints, bearer authentication, Docker packaging, CI, and deterministic tests.
