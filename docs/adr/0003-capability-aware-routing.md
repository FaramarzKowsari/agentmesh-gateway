# ADR 0003: Capability-aware routing before policy scoring

Status: accepted

## Context

AgentMesh v0.2 already enforced protocol-losslessness constraints, such as requiring a native Responses adapter when a request carries semantics that cannot be translated safely. The adaptive-router roadmap also needs model/provider capability constraints so a low-cost or low-latency provider cannot win a route that it is not capable of serving correctly.

A capability system must not break existing provider configurations that predate explicit capability declarations.

## Decision

Provider specifications may declare a `capabilities` list. The initial vocabulary is intentionally narrow and maps only to behavior AgentMesh can currently reason about:

- `text`
- `tools`
- `reasoning`
- `native_responses_tools`

Routing uses capabilities as a hard eligibility constraint before any latency, cost, quality, weight, or ordering policy is applied.

Request requirements are derived from the normalized request:

- all currently supported requests require `text`;
- custom-function definitions, tool calls, or tool results require `tools`;
- Responses reasoning controls, reasoning input items, or reasoning include fields require `reasoning`;
- recognized non-function Responses-native tools additionally require `native_responses_tools`.

Protocol constraints remain independent hard gates. For example, satisfying the `reasoning` capability does not allow a Chat Completions adapter to receive a Responses request that has already been marked native-only.

## Backward compatibility

If `capabilities` is omitted, AgentMesh derives the same assumptions used before this ADR:

- `openai`: `text`, `tools`
- `anthropic`: `text`, `tools`
- `responses`: `text`, `tools`, `reasoning`, `native_responses_tools`

If `capabilities` is supplied explicitly, it is authoritative. An empty list therefore makes the provider ineligible for the currently supported request surface.

## Consequences

- Adaptive routing gains an explicit feasibility layer before optimization.
- Operators can prevent a model/provider from receiving tool or reasoning traffic even if its adapter shape would otherwise allow it.
- `/admin/providers` can expose effective capabilities for debugging and experiments.
- Existing configuration remains valid without modification.
- The initial vocabulary does not claim vision, audio, context-window, or structured-output routing; those should be added only when the request model and tests can express the corresponding requirements reliably.

## Research direction

This hard capability gate creates a clean feasible-action set for future routing experiments. Later policies can optimize latency, cost, quality, quota pressure, or learned reward only over providers that satisfy protocol and capability constraints, avoiding invalid comparisons between infeasible actions.
