# Changelog

All notable changes to AgentMesh Gateway are documented in this file.

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
